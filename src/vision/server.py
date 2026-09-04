import os, base64, cv2, requests
from fastapi import FastAPI

OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama-new:11434")
VLM    = os.environ.get("VLM_MODEL", "llava")
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://perception:8000")

app = FastAPI(title="robotcar-vision")

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
    return {"ok": True, "vlm": VLM}

@app.post("/capture")
def capture(prompt: str = "Describe this scene briefly and factually."):
    img = _grab_jpeg_b64()
    if img is None:
        return {"ok": False, "error": "camera read failed"}
    r = requests.post(f"{OLLAMA}/api/generate",
                      json={"model": VLM, "prompt": prompt, "images": [img], "stream": False},
                      timeout=180)
    r.raise_for_status()
    return {"ok": True, "description": r.json().get("response", "").strip()}
