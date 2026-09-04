#!/bin/bash
# ============================================================
# M49：把「卸載＋等待＋載入」整段包進同一把鎖，徹底堵住交錯
#
#   M48 的世代檢查是「逐段檢查」，段與段之間還是有縫隙可能被
#   插隊（M48 驗證時又觀察到 llava 消失後沒有回來）。
#   這次改法：整個 _apply_async() 的「真正動 GPU 的部分」包在
#   一把鎖（_apply_lock）裡，同一時間只有一個世代能執行；
#   拿到鎖時再確認一次自己是不是最新世代，不是就直接放棄，
#   不會有任何跟別的世代交錯執行的可能。
#
#   另外加了內部時間軸紀錄檔（data/mode_trace.log），每一步
#   都會記下時間戳＋世代編號＋做了什麼，之後如果還有問題，
#   直接看機器實際做了什麼，不用再靠外部輪詢反推。
#
#   驗證：跟 M48 一樣的壓力測試（manage→observe 只隔 1 秒），
#   跑完後把 trace 檔案原文印出來，連同 GPU 輪詢結果一起看。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
echo "== [1/7] 備份 modes.py，並清空舊的 trace 檔（如果有）=="
cp -v acoustic_app/modes.py "acoustic_app/modes.py.bak.$TS"
rm -f data/mode_trace.log

echo "== [2/7] 寫入加了 apply_lock 與 trace log 的 modes.py =="
cat > acoustic_app/modes.py <<'PYEOF'
# acoustic_app/modes.py — JN1 五模式（注意力分配）管理
#
# 理念：全部能力常駐，但 GPU 大模型「一次一個」隨模式切換。
# 切模式＝卸掉不要的大模型、載上要的（背景），並寫下目前模式供各頁顯示。
#
# 大模型槽 big：None=不載大模型 / "chat"=qwen / "vlm"=llava
# 由 server.py 匯入：import modes；提供 get_mode() / set_mode() / MODES
#
# v5（M49）改動：
#   - 不再逐段檢查世代（M48 的做法有縫隙）。改成把整個「卸載+等待+
#     載入」包進 _apply_lock，同一時間只有一個世代能真正動 GPU；
#     拿到鎖時再確認一次自己是不是最新世代，不是就直接放棄。
#     這樣不會有任何跟別的世代交錯執行的可能。
#   - 新增 data/mode_trace.log：每一步都記時間戳＋世代編號＋動作，
#     方便直接看機器實際做了什麼，不必靠外部輪詢反推。
# v4（M48）：世代編號防跨呼叫競速（逐段檢查版，已被 v5 取代其機制）。
# v3（M47）：卸載後輪詢等舊模型真的消失才載新的，避免單次切換內 OOM。
# v2：chat_model/vlm_model 可在管理頁即時覆寫；原始查詢 ollama 狀態。

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
TRACE_FILE = os.path.join(_HERE, "..", "data", "mode_trace.log")

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

_gen_lock = threading.Lock()
_generation = 0
_apply_lock = threading.Lock()  # 同一時間只有一個世代能真正動 GPU


def _bump_generation():
    global _generation
    with _gen_lock:
        _generation += 1
        return _generation


def _is_current(gen):
    with _gen_lock:
        return gen == _generation


def _trace(gen, msg):
    try:
        os.makedirs(os.path.dirname(TRACE_FILE), exist_ok=True)
        with open(TRACE_FILE, "a") as f:
            f.write("%.3f gen=%s %s\n" % (time.time(), gen, msg))
    except Exception:
        pass


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


def _wait_gone(model, timeout=10, interval=0.5):
    """等到指定模型真的從 GPU 上消失。在 _apply_lock 裡面呼叫，
    不會有別的世代插隊，所以不需要再夾世代檢查。"""
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


def _apply_async(big, gen):
    _trace(gen, "queued (等鎖) big=%s" % big)
    with _apply_lock:
        if not _is_current(gen):
            _trace(gen, "拿到鎖時已經過時，放棄，不碰 GPU")
            return
        _trace(gen, "拿到鎖，開始執行")

        chat_model = get_chat_model()
        vlm_model = get_vlm_model()

        if big != "chat":
            _trace(gen, "卸載 chat_model=%s" % chat_model)
            _ollama_unload(chat_model)
            ok = _wait_gone(chat_model, timeout=10)
            _trace(gen, "chat 卸載等待結果=%s" % ok)

        if big != "vlm":
            _trace(gen, "卸載 vlm_model=%s" % vlm_model)
            _ollama_unload(vlm_model)
            ok = _wait_gone(vlm_model, timeout=10)
            _trace(gen, "vlm 卸載等待結果=%s" % ok)

        if big == "chat":
            _trace(gen, "載入 chat_model=%s" % chat_model)
            r = _ollama_warm_safe(chat_model)
            _trace(gen, "chat 載入結果=%s" % (str(r)[:150] if r else r))
        elif big == "vlm":
            _trace(gen, "載入 vlm_model=%s" % vlm_model)
            r = _ollama_warm_safe(vlm_model)
            _trace(gen, "vlm 載入結果=%s" % (str(r)[:150] if r else r))

        _trace(gen, "完成")


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
    _trace(gen, "set_mode 呼叫，mode=%s" % mode)
    threading.Thread(target=_apply_async, args=(m["big"], gen), daemon=True).start()
    return {"ok": True, "mode": mode, "config": m, "switching": bool(m["big"]), "gen": gen}
PYEOF
python3 -c "import ast; ast.parse(open('acoustic_app/modes.py').read())" && echo "modes.py 語法 OK" || { echo "❌ 語法錯誤，停止"; exit 1; }

echo "== [3/7] 重啟 jn1-web（給足時間，不用短 sleep 誤判） =="
systemctl --user restart jn1-web
for i in 1 2 3 4 5 6; do
  sleep 2
  systemctl --user is-active --quiet jn1-web && echo "jn1-web active（第 $((i*2)) 秒）"
done

echo "== [4/7] 取帳密（不印出來，只用來 curl）=="
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

echo "== [5/7] 確認起點乾淨（輪詢直到 GPU 真的空了）=="
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 2
  STATUS=$(curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu)
  echo "起點確認 第${i}次（+$((i*2))秒）：$STATUS"
  echo "$STATUS" | grep -q '"models":\[\]' && { echo "GPU 已清空，開始壓力測試"; break; }
done

echo ""
echo "== [6/7] 跨呼叫競速壓力測試（manage → observe 只隔 1 秒）=="
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo " ← manage 觸發"
sleep 1
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"observe"}'
echo " ← observe 觸發（只隔 1 秒）"

for i in 1 2 3 4 5 6; do
  echo "第 ${i} 次（觸發後約 $((i*5)) 秒）："
  curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu
  echo ""
  sleep 5
done

echo "--- 收工前切回 manage，釋放 GPU ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""
sleep 3

unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [7/7] 印出內部時間軸紀錄（原始檔案內容），git commit + push =="
echo "--- data/mode_trace.log 原文 ---"
cat data/mode_trace.log

git add acoustic_app/modes.py
git status --short
git commit -m "M49: 用 apply_lock 包住整段卸載/載入，徹底堵住跨世代交錯

- M48 的逐段世代檢查有縫隙（驗證時 llava 又消失且沒回來）
- 改法：整個 _apply_async() 的 GPU 操作包進 _apply_lock，
  同一時間只有一個世代能真正動 GPU；拿到鎖時再確認一次是否
  還是最新世代，不是就直接放棄，不會有任何交錯執行的可能
- 新增 data/mode_trace.log：每一步記時間戳＋世代＋動作，
  之後有問題可以直接看機器做了什麼，不必再靠外部輪詢反推

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"

echo "--- push ---"
git push origin jn1-work
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git ls-remote origin jn1-work | awk '{print $1}')
echo "本地 HEAD: $LOCAL_HEAD"
echo "遠端 HEAD: $REMOTE_HEAD"
[ "$LOCAL_HEAD" = "$REMOTE_HEAD" ] && echo "✅ push 確認成功" || echo "❌ push 沒有真的成功，回報這兩行給我"

echo ""
echo "############################################################"
echo "M49 完成。請把 [6/7] 的 6 次輪詢原始 JSON，"
echo "以及 [7/7] 印出來的 data/mode_trace.log 原文，"
echo "整段一起貼給我——這次除了外部觀察，還能對照機器內部實際"
echo "每一步做了什麼、什麼時間點做的，不用再靠猜的。"
echo "############################################################"
