"""robotcar-ocr — PaddleOCR (PP-OCR, Chinese) on CPU. On-demand module.
Reads a frame from perception (single camera owner) when up, else own capture.
We do NOT use a VLM to OCR (VLM OCR looks right but is often wrong, M2_PLAN §A).
"""
import os

import numpy as np
import requests
from fastapi import FastAPI

PERCEPTION = os.environ.get("PERCEPTION_URL", "http://perception:8000")
LANG = os.environ.get("OCR_LANG", "ch")

app = FastAPI(title="robotcar-ocr", version="1.0.0")
_ocr = None


def _load():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(use_angle_cls=True, lang=LANG, show_log=False)
    return _ocr


def _get_frame():
    import cv2
    try:
        r = requests.get(f"{PERCEPTION}/frame.jpg", timeout=5)
        if r.status_code == 200 and r.content:
            arr = np.frombuffer(r.content, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        pass
    cap = cv2.VideoCapture(0)
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    return frame if ok else None


def _run(img):
    ocr = _load()
    try:
        res = ocr.ocr(img)
    except Exception:
        res = ocr.predict(img)
    lines = []
    try:
        for page in res:
            if page is None:
                continue
            for line in page:
                box, txt = line[0], line[1]
                text = txt[0] if isinstance(txt, (list, tuple)) else txt
                conf = float(txt[1]) if isinstance(txt, (list, tuple)) and len(txt) > 1 else None
                lines.append({"text": text, "conf": conf, "box": box})
    except Exception:
        pass
    return lines


@app.get("/health")
def health():
    try:
        _load()
        return {"ok": True, "lang": LANG}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/read")
def read():
    img = _get_frame()
    if img is None:
        return {"ok": False, "error": "no frame"}
    lines = _run(img)
    text = "".join(l["text"] for l in lines)
    return {"ok": True, "text": text, "lines": lines}
