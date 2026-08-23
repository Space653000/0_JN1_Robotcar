import os, base64, cv2
from fastapi import FastAPI

app = FastAPI(title="robotcar-vision", version="0.1.0-vision-lite")

def _grab_jpeg_b64():
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
    return {"ok": True, "mode": "vision-lite (text LLM only, no VLM GPU)"}

@app.post("/capture")
def capture(prompt: str = "Describe this scene briefly and factually."):
    """Grab camera frame as JPEG base64.
    Real VLM processing deferred to brain via text LLM (qwen2.5).
    This avoids GPU OOM issues on Jetson Orin NX (8GB VRAM)."""
    img = _grab_jpeg_b64()
    if img is None:
        return {"ok": False, "error": "camera read failed"}
    return {"ok": True, "image_b64": img, "note": "VLM inference deferred to brain"}
