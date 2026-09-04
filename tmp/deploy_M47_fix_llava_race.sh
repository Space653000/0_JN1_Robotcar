#!/bin/bash
# ============================================================
# M47：修 observe 模式切換時的競速 OOM
#   問題：卸載 qwen 後「馬上」叫 llava 上，卸載是背景非同步，
#         GPU 記憶體常常還沒真的釋放乾淨，導致 llava 載入瞬間
#         偶發性 cudaMalloc OOM（即使最後仍會補完成功）。
#   修法：卸載後改成「輪詢 /api/ps 等到舊模型真的消失」才載新的，
#         並加一次自動重試當保險。
#   驗證方式：直接走真正會用到的 /api/mode API 切換，
#             不繞道直接打 ollama——確保修的是實際會用到的路徑。
# 全程只印原始輸出，不產生摘要表格。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
echo "== [1/6] 備份 modes.py =="
cp -v acoustic_app/modes.py "acoustic_app/modes.py.bak.$TS"

echo "== [2/6] 寫入修好競速問題的 modes.py =="
cat > acoustic_app/modes.py <<'PYEOF'
# acoustic_app/modes.py — JN1 五模式（注意力分配）管理
#
# 理念：全部能力常駐，但 GPU 大模型「一次一個」隨模式切換。
# 切模式＝卸掉不要的大模型、載上要的（背景），並寫下目前模式供各頁顯示。
#
# 大模型槽 big：None=不載大模型 / "chat"=qwen / "vlm"=llava
# 由 server.py 匯入：import modes；提供 get_mode() / set_mode() / MODES
#
# v3（M47）新增：
#   - 卸載後改「輪詢 /api/ps 等舊模型真的消失」才載新的，避免競速 OOM。
#   - _ollama_warm_safe()：載入失敗（例如暫時性 OOM）自動重試一次。
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
    """載入並常駐；第一次若失敗（例如卸載競速造成的暫時性 OOM），
    等一下再試一次。回傳最後一次的原始回應文字。"""
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


def _wait_gone(model, timeout=10, interval=0.5):
    """等到指定模型真的從 GPU 上消失（輪詢原始 /api/ps），避免下一個模型
    在還沒真的釋放記憶體時搶著載入、造成暫時性 OOM。逾時就放棄等待，繼續往下走。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
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


def _apply_async(big):
    chat_model = get_chat_model()
    vlm_model = get_vlm_model()

    if big != "chat":
        _ollama_unload(chat_model)
        _wait_gone(chat_model, timeout=10)
    if big != "vlm":
        _ollama_unload(vlm_model)
        _wait_gone(vlm_model, timeout=10)

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
    threading.Thread(target=_apply_async, args=(m["big"],), daemon=True).start()
    return {"ok": True, "mode": mode, "config": m, "switching": bool(m["big"])}
PYEOF
python3 -c "import ast; ast.parse(open('acoustic_app/modes.py').read())" && echo "modes.py 語法 OK" || { echo "❌ 語法錯誤，停止"; exit 1; }

echo "== [3/6] 重啟 jn1-web =="
systemctl --user restart jn1-web
sleep 2

echo "== [4/6] 取帳密（不印出來，只用來 curl）=="
set -a
source acoustic_app/.env
set +a

echo "== [5/6] 走真正的 /api/mode API 做端到端驗證（不繞道直打 ollama）=="

echo "--- 先切回 manage，確保起點乾淨 ---"
curl -sS -u "$ACOUSTIC_USER:$ACOUSTIC_PASS" -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""
sleep 5
echo "--- manage 模式下 GPU 現況（應該接近空） ---"
curl -sS -u "$ACOUSTIC_USER:$ACOUSTIC_PASS" http://127.0.0.1:8011/api/mode/gpu
echo ""

echo "--- 切到 observe（這一刀是真正的考驗） ---"
curl -sS -u "$ACOUSTIC_USER:$ACOUSTIC_PASS" -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"observe"}'
echo ""

echo "--- 切換後每 5 秒查一次 GPU 狀態，連續 4 次，全部印出原始內容 ---"
for i in 1 2 3 4; do
  echo "第 ${i} 次（切換後約 $((i*5)) 秒）："
  curl -sS -u "$ACOUSTIC_USER:$ACOUSTIC_PASS" http://127.0.0.1:8011/api/mode/gpu
  echo ""
  sleep 5
done

echo "--- 收工前切回 manage，釋放 GPU ---"
curl -sS -u "$ACOUSTIC_USER:$ACOUSTIC_PASS" -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""

unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [6/6] git commit + push（用 commit id 比對驗證，不是用 git 自己講的話）=="
git add acoustic_app/modes.py
git status --short
git commit -m "M47: 修 observe 模式切換的競速 OOM

- _apply_async(): 卸載後改輪詢 /api/ps 等舊模型真的消失，才載新模型
- 新增 _ollama_warm_safe(): 載入失敗自動重試一次
- 解決現象：qwen 卸載回應是非同步的，llava 緊接著載入時常撞上還沒
  釋放乾淨的 VRAM，造成一次性 cudaMalloc OOM（雖然最後仍會補完成功）

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
echo "M47 完成。請把 [5/6] 那四次輪詢的原始 JSON 整段貼給我——"
echo "我要親眼看每一次 models 陣列裡有沒有出現 llava、有沒有 error 欄位，"
echo "不要先幫我判斷『看起來成功了』。"
echo "############################################################"
