import os, json, base64, cv2, requests
from fastapi import FastAPI

# M59.6：VLM 模型選擇改以 modes.py 的 mode_config.json 為單一事實來源。
# M51 當時只修了相機競爭（改走 PERCEPTION_URL），沒修這裡——vision 自己
# 讀一份 VLM_MODEL 環境變數，跟 modes.py 的 vlm_model（存在
# data/mode_config.json）是兩條沒有連接的設定路徑，剛好都是 moondream
# 只是巧合。這裡改成優先讀 mode_config.json，VLM_MODEL 降級為「檔案
# 讀不到時」的備援，並在啟動與 /health 都記錄目前來源，讓分岔的瞬間
# 可被看見（不是靜默各走各的）。
OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama-new:11434")
_VLM_ENV_FALLBACK = os.environ.get("VLM_MODEL", "llava")
MODE_CONFIG_FILE = os.environ.get("JN1_MODE_CONFIG_FILE", "/appdata/mode_config.json")
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://perception:8000")

app = FastAPI(title="robotcar-vision")


def _current_vlm():
    """回傳 (model_name, source)。source 是 'mode_config' 或 'env_fallback'，
    讓呼叫端與 /health 都能看見現在到底是哪條路徑在決定模型。"""
    try:
        with open(MODE_CONFIG_FILE) as f:
            cfg = json.load(f)
        v = cfg.get("vlm_model")
        if v:
            return v, "mode_config"
    except Exception as e:
        print(f"[VISION] 讀不到 {MODE_CONFIG_FILE}（{type(e).__name__}），改用 env fallback")
    return _VLM_ENV_FALLBACK, "env_fallback"


print(f"[VISION] 啟動，目前 VLM 來源={_current_vlm()}")


def _grab_jpeg_b64():
    # 從 perception 服務獲取 JPEG（避免與其他服務搶 /dev/video0）
    try:
        r = requests.get(f"{PERCEPTION_URL}/frame.jpg", timeout=5)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode()
    except Exception as e:
        print(f"[VISION] perception proxy failed: {e}")

    # 備用：直接打開相機（若 perception 故障）
    cap = cv2.VideoCapture(0)
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        return None
    ok, buf = cv2.imencode(".jpg", frame)
    return base64.b64encode(buf).decode() if ok else None

@app.get("/health")
def health():
    model, source = _current_vlm()
    return {"ok": True, "vlm": model, "vlm_source": source}

@app.post("/capture")
def capture(prompt: str = "Describe this scene briefly and factually."):
    img = _grab_jpeg_b64()
    if img is None:
        return {"ok": False, "error": "camera read failed"}
    model, source = _current_vlm()
    r = requests.post(f"{OLLAMA}/api/generate",
                      json={"model": model, "prompt": prompt, "images": [img], "stream": False},
                      timeout=180)
    r.raise_for_status()
    return {"ok": True, "description": r.json().get("response", "").strip(),
            "vlm": model, "vlm_source": source}
