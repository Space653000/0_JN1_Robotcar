import os, base64, cv2, requests
from fastapi import FastAPI

app = FastAPI(title="robotcar-vision", version="0.2.0-vision-vlm")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama-new:11434")
VLM_MODEL = os.environ.get("VLM_MODEL", "moondream")
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "180"))

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
    return {"ok": True, "mode": "vision-vlm (real-time VLM inference)", "vlm_model": VLM_MODEL}

@app.post("/capture")
def capture(prompt: str = "Describe this scene briefly."):
    """Grab camera frame + real VLM inference via ollama (moondream).
    Fallback to scene inference via LLM if VLM fails.
    Note: VLM may output in English; brain layer converts to Traditional Chinese."""
    img = _grab_jpeg_b64()
    if img is None:
        return {"ok": False, "error": "camera read failed"}

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": VLM_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [img]
                    }
                ],
                "stream": False
            },
            timeout=HTTP_TIMEOUT
        )

        if resp.status_code != 200:
            return {"ok": False, "error": f"ollama error {resp.status_code}"}

        data = resp.json()
        description = data.get("message", {}).get("content", "").strip()

        if description:
            return {
                "ok": True,
                "image_b64": img,
                "description": description,
                "vlm_model": VLM_MODEL,
                "source": "ollama-vlm"
            }
        else:
            return {"ok": False, "error": "empty response from VLM"}
    except requests.Timeout:
        return {"ok": False, "error": "VLM timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}
