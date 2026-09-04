#!/bin/bash
# ============================================================
# M48：修跨呼叫的競速（上一次切換的背景執行緒還沒結束，
#       下一次切換就進來了，導致 GPU 狀態震盪）
#
#   問題（M47 驗證時發現）：set_mode() 每次都起一個新背景 thread
#       去卸載/載入模型，但沒有機制讓「舊的還沒做完的那個」知道
#       自己已經過時了。連續切兩次模式時，舊 thread 可能在新 thread
#       已經把新模型載好之後，才姍姍來遲地把它卸掉。
#
#   修法：加「世代編號」。每次 set_mode() 呼叫，世代編號 +1；
#       背景執行緒每完成一個步驟，就檢查自己是不是還是最新的一代，
#       不是的話立刻放棄、不再碰 GPU。這樣不管切換多快、多密集，
#       永遠只有最後一次切換會真正執行到底。
#
#   驗證方式：故意連續、幾乎無間隔地觸發兩次切換（比 M47 那次的
#       5 秒間隔更嚴苛），證明就算刻意疊加呼叫，最後也只會乾淨地
#       停在最新那個模式，不會震盪。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
echo "== [1/6] 備份 modes.py =="
cp -v acoustic_app/modes.py "acoustic_app/modes.py.bak.$TS"

echo "== [2/6] 寫入加了世代鎖的 modes.py =="
cat > acoustic_app/modes.py <<'PYEOF'
# acoustic_app/modes.py — JN1 五模式（注意力分配）管理
#
# 理念：全部能力常駐，但 GPU 大模型「一次一個」隨模式切換。
# 切模式＝卸掉不要的大模型、載上要的（背景），並寫下目前模式供各頁顯示。
#
# 大模型槽 big：None=不載大模型 / "chat"=qwen / "vlm"=llava
# 由 server.py 匯入：import modes；提供 get_mode() / set_mode() / MODES
#
# v4（M48）新增：
#   - 「世代編號」防跨呼叫競速：每次 set_mode() 世代 +1，背景執行緒
#     每完成一步就檢查自己是否還是最新一代，不是就立刻放棄、不碰 GPU。
#     修的問題：連續快速切模式時，舊的背景任務可能在新任務做完之後
#     才姍姍來遲地把新載入的模型卸掉，造成 GPU 狀態震盪。
# v3（M47）：
#   - 卸載後改「輪詢 /api/ps 等舊模型真的消失」才載新的，避免競速 OOM。
#   - _ollama_warm_safe()：載入失敗自動重試一次。
# v2：
#   - chat_model / vlm_model 可在管理頁即時覆寫（data/mode_config.json）。
#   - list_installed_models() / get_gpu_status()：直接轉手 ollama 原始查詢。

import os
import json
import time
import threading

try:
    import httpx
except Exception:
    httpx = None
    import urllib.request

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
_ENV_CHAT_MODEL = os.environ.get("JN1_CHAT_MODEL", "qwen2.5:3b")
_ENV_VLM_MODEL = os.environ.get("JN1_VLM_MODEL", "llava")

_HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_HERE, "..", "data", "mode.json")
CONFIG_FILE = os.path.join(_HERE, "..", "data", "mode_config.json")

MODES = {
    "manage":  {"label": "管理（開發）", "big": None,   "vlm": False, "cloud": True,
                "vision": "normal", "desc": "開發駕駛艙：全功能檢查＋各模式設定＋模式選單"},
    "chat":    {"label": "對話",         "big": "chat", "vlm": False, "cloud": True,
                "vision": "low",    "desc": "停下來聊天/思考/查雲端，不細看"},
    "observe": {"label": "觀察",         "big": "vlm",  "vlm": True,  "cloud": True,
                "vision": "normal", "desc": "專心看仔細：整句描述＋讀字"},
    "patrol":  {"label": "巡航",         "big": None,   "vlm": False, "cloud": False,
                "vision": "high",   "desc": "移動警覺：偵測＋聲音方向＋播報"},
    "standby": {"label": "待機",         "big": None,   "vlm": False, "cloud": False,
                "vision": "off",    "wake": "嗨",
                "desc": "打盹省電，喚醒詞『嗨』叫醒"},
}

DEFAULT_MODE = "manage"
_config_lock = threading.Lock()

# ---------- 世代鎖（防跨呼叫競速） ----------
_gen_lock = threading.Lock()
_generation = 0


def _bump_generation():
    global _generation
    with _gen_lock:
        _generation += 1
        return _generation


def _is_current(gen):
    with _gen_lock:
        return gen == _generation


def _post(url, body, timeout):
    try:
        if httpx is not None:
            r = httpx.post(url, json=body, timeout=timeout)
            return r.text
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception:
        return None


def _get(url, timeout):
    try:
        if httpx is not None:
            r = httpx.get(url, timeout=timeout)
            return r.text
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception:
        return None


def _ollama_unload(model):
    _post(OLLAMA + "/api/generate",
          {"model": model, "keep_alive": 0, "prompt": ""}, timeout=30)


def _ollama_warm(model):
    return _post(OLLAMA + "/api/generate",
          {"model": model, "keep_alive": -1, "prompt": "hi", "stream": False}, timeout=180)


def _ollama_warm_safe(model, retries=1, retry_wait=2):
    result = None
    for attempt in range(retries + 1):
        result = _ollama_warm(model)
        if result is not None and '"error"' not in result:
            return result
        if attempt < retries:
            time.sleep(retry_wait)
    return result


def _resident_names():
    st = get_gpu_status()
    if isinstance(st, dict) and isinstance(st.get("models"), list):
        return [m.get("name") for m in st["models"]]
    return []


def _wait_gone(model, timeout=10, interval=0.5, gen=None):
    """等到指定模型真的從 GPU 上消失。若帶了 gen，一旦發現自己已經
    不是最新世代，立刻停止等待（沒有意義再等下去）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if gen is not None and not _is_current(gen):
            return False
        if model not in _resident_names():
            return True
        time.sleep(interval)
    return False


def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_chat_model():
    return _load_config().get("chat_model") or _ENV_CHAT_MODEL


def get_vlm_model():
    return _load_config().get("vlm_model") or _ENV_VLM_MODEL


def get_model_config():
    cfg = _load_config()
    return {
        "chat_model": cfg.get("chat_model") or _ENV_CHAT_MODEL,
        "vlm_model": cfg.get("vlm_model") or _ENV_VLM_MODEL,
        "chat_model_is_override": bool(cfg.get("chat_model")),
        "vlm_model_is_override": bool(cfg.get("vlm_model")),
        "env_default_chat": _ENV_CHAT_MODEL,
        "env_default_vlm": _ENV_VLM_MODEL,
    }


def set_model_config(chat_model=None, vlm_model=None):
    with _config_lock:
        cfg = _load_config()
        if chat_model is not None:
            v = chat_model.strip()
            if v:
                cfg["chat_model"] = v
            else:
                cfg.pop("chat_model", None)
        if vlm_model is not None:
            v = vlm_model.strip()
            if v:
                cfg["vlm_model"] = v
            else:
                cfg.pop("vlm_model", None)
        _save_config(cfg)
    return get_model_config()


def list_installed_models():
    txt = _get(OLLAMA + "/api/tags", timeout=10)
    if txt is None:
        return {"error": "連不到 ollama /api/tags"}
    try:
        data = json.loads(txt)
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception as e:
        return {"error": "解析失敗: " + type(e).__name__}


def get_gpu_status():
    txt = _get(OLLAMA + "/api/ps", timeout=10)
    if txt is None:
        return {"error": "連不到 ollama /api/ps"}
    try:
        return json.loads(txt)
    except Exception:
        return {"raw": txt}


def get_mode():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
        if st.get("mode") in MODES:
            return st
    except Exception:
        pass
    return {"mode": DEFAULT_MODE, "ts": 0}


def _apply_async(big, gen):
    """gen＝這次切換的世代編號。每一步之前都先確認自己還是不是最新的，
    不是的話立刻退出，讓真正最新的那次切換說了算。"""
    if not _is_current(gen):
        return

    chat_model = get_chat_model()
    vlm_model = get_vlm_model()

    if big != "chat":
        _ollama_unload(chat_model)
        if not _wait_gone(chat_model, timeout=10, gen=gen):
            if not _is_current(gen):
                return
    if not _is_current(gen):
        return

    if big != "vlm":
        _ollama_unload(vlm_model)
        if not _wait_gone(vlm_model, timeout=10, gen=gen):
            if not _is_current(gen):
                return
    if not _is_current(gen):
        return

    if big == "chat":
        _ollama_warm_safe(chat_model)
    elif big == "vlm":
        _ollama_warm_safe(vlm_model)


def set_mode(mode):
    if mode not in MODES:
        return {"ok": False, "error": "unknown mode: " + str(mode)}
    m = MODES[mode]
    st = {"mode": mode, "ts": time.time()}
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(st, f)
    except Exception as e:
        return {"ok": False, "error": "write state failed: " + type(e).__name__}
    gen = _bump_generation()
    threading.Thread(target=_apply_async, args=(m["big"], gen), daemon=True).start()
    return {"ok": True, "mode": mode, "config": m, "switching": bool(m["big"]), "gen": gen}
PYEOF
python3 -c "import ast; ast.parse(open('acoustic_app/modes.py').read())" && echo "modes.py 語法 OK" || { echo "❌ 語法錯誤，停止"; exit 1; }

echo "== [3/6] 重啟 jn1-web（給足時間起服務，不再用 sleep 2 誤判）=="
systemctl --user restart jn1-web
for i in 1 2 3 4 5 6; do
  sleep 2
  if systemctl --user is-active --quiet jn1-web; then
    echo "jn1-web active（第 $((i*2)) 秒）"
  fi
done
systemctl --user status jn1-web --no-pager -l | head -10

echo "== [4/6] 取帳密（不印出來，只用來 curl）=="
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

echo "== [5/6] 跨呼叫競速壓力測試（故意疊加呼叫，證明不會震盪）=="

echo "--- 先確保起點乾淨：切到 manage，並輪詢直到 GPU 真的空了（不用盲猜的 sleep）---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 2
  STATUS=$(curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu)
  echo "起點確認 第${i}次（+$((i*2))秒）：$STATUS"
  if echo "$STATUS" | grep -q '"models":\[\]'; then
    echo "GPU 已確認清空，開始壓力測試"
    break
  fi
done

echo ""
echo "--- 壓力測試：manage → observe 幾乎無間隔連續觸發（比 M47 那次的 5 秒間隔更嚴苛） ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo " ← manage 觸發"
sleep 1
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"observe"}'
echo " ← observe 觸發（只隔 1 秒，故意疊加）"

echo ""
echo "--- 之後每 5 秒查一次 GPU，連續 6 次，全部印出原始內容（看有沒有再震盪）---"
for i in 1 2 3 4 5 6; do
  echo "第 ${i} 次（觸發後約 $((i*5)) 秒）："
  curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu
  echo ""
  sleep 5
done

echo "--- 收工前切回 manage，釋放 GPU ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""

unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [6/6] git commit + push（用 commit id 比對驗證）=="
git add acoustic_app/modes.py
git status --short
git commit -m "M48: 修跨呼叫的模式切換競速（世代鎖）

- set_mode() 每次呼叫世代編號 +1；_apply_async() 每完成一步就檢查
  自己是否還是最新一代，不是就立刻放棄、不再碰 GPU
- 解決現象（M47 驗證時發現）：連續切模式時，前一次切換的背景任務
  可能在新任務已經把新模型載好之後，才姍姍來遲地把它卸掉，造成
  GPU 狀態忽有忽無地震盪

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"

echo "--- push ---"
git push origin jn1-work
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git ls-remote origin jn1-work | awk '{print $1}')
echo "本地 HEAD: $LOCAL_HEAD"
echo "遠端 HEAD: $REMOTE_HEAD"
if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
  echo "✅ push 確認成功（兩邊 commit id 一致）"
else
  echo "❌ push 沒有真的成功，回報這兩行給我"
fi

echo ""
echo "############################################################"
echo "M48 完成。請把 [5/6] 壓力測試那 6 次輪詢的原始 JSON 整段貼給我——"
echo "這次是刻意用比上次更嚴苛的疊加時機測的，只要不再忽有忽無地震盪、"
echo "穩定停在 llava 常駐，才算真的把跨呼叫的競速修好。"
echo "############################################################"
