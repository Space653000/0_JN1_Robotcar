"""robotcar-depth — Depth Anything V2 (Small) monocular depth. On-demand module.
Software stand-in for a depth camera until the RealSense D435i arrives: gives a
RELATIVE depth map from the plain webcam. Output is qualitative (nearer/farther),
NOT metres. GPU when available -> heavy on-demand -> memory gate. Frame from
perception when up.
"""
import os

import numpy as np
import requests
from fastapi import FastAPI

PERCEPTION = os.environ.get("PERCEPTION_URL", "http://perception:8000")
MODEL_ID = os.environ.get("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Small-hf")

app = FastAPI(title="robotcar-depth", version="1.0.0")
_pipe = None


def _load():
    global _pipe
    if _pipe is None:
        import torch
        from transformers import pipeline
        dev = 0 if torch.cuda.is_available() else -1
        _pipe = pipeline("depth-estimation", model=MODEL_ID, device=dev)
    return _pipe


def _get_frame_pil():
    import cv2
    from PIL import Image
    data = None
    try:
        r = requests.get(f"{PERCEPTION}/frame.jpg", timeout=5)
        if r.status_code == 200 and r.content:
            data = r.content
    except Exception:
        pass
    if data is not None:
        arr = np.frombuffer(data, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    else:
        cap = cv2.VideoCapture(0)
        try:
            ok, bgr = cap.read()
        finally:
            cap.release()
        if not ok:
            return None
    return Image.fromarray(bgr[:, :, ::-1])


def _summarise(depth: np.ndarray) -> str:
    h, w = depth.shape
    roi = depth[int(h * 0.3):, :]
    thirds = np.array_split(roi, 3, axis=1)
    names = ["左邊", "正前方", "右邊"]
    means = [float(t.mean()) for t in thirds]
    nearest = names[int(np.argmax(means))]
    order = ", ".join(f"{names[i]}" for i in np.argsort(means)[::-1])
    return f"看起來{nearest}最近(相對距離由近到遠:{order})。這是單目相對深度,不是實際公尺數。"


@app.get("/health")
def health():
    try:
        import torch
        return {"ok": True, "model": MODEL_ID, "cuda": bool(torch.cuda.is_available())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/estimate")
def estimate():
    img = _get_frame_pil()
    if img is None:
        return {"ok": False, "error": "no frame"}
    out = _load()(img)
    depth = np.array(out["depth"], dtype="float32")
    return {"ok": True, "summary_zh": _summarise(depth),
            "shape": list(depth.shape),
            "min": float(depth.min()), "max": float(depth.max())}
