"""robotcar-perception v1 — real object detection via YOLO.

Real-time object detection using YOLO (ultralytics yolo11n by default).
Single camera owner: perception exclusively uses /dev/video0.

Endpoints:
  GET  /health          — service status + loaded model
  POST /state           — run inference, return detected objects with confidence + Chinese labels
  GET  /frame.jpg       — current camera frame (JPEG for debugging)
"""
import os
import base64
import cv2
import json
import logging
import time
from fastapi import FastAPI
from threading import Thread, Lock
from ultralytics import YOLO

# Configuration
YOLO_MODEL = os.environ.get("YOLO_MODEL", "yolo11n")  # ultralytics model name
CONFIDENCE_THRESHOLD = float(os.environ.get("CONF_THRESHOLD", "0.5"))
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
FRAME_RATE = int(os.environ.get("FRAME_RATE", "30"))

# Load Chinese labels
LABELS_FILE = os.path.join(os.path.dirname(__file__), "labels_zh.json")
try:
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        LABELS_ZH = json.load(f)
except Exception as e:
    logging.warning(f"Failed to load labels_zh.json: {e}")
    LABELS_ZH = {}

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("robotcar-perception")

# FastAPI app
app = FastAPI(title="robotcar-perception", version="1.0.0")

# Global state
_model = None
_cap = None
_latest_detections = None
_state_lock = Lock()  # 序列化：保護相機讀取 + GPU 推論
_last_inference_time = 0.0

def _init_model():
    """Initialize YOLO model."""
    global _model
    try:
        logger.info(f"Loading YOLO model: {YOLO_MODEL}")
        model_path = YOLO_MODEL

        # Try direct path first, then model name
        from pathlib import Path
        if not Path(model_path).exists():
            cache_path = Path.home() / '.cache' / 'yolov8' / f'{YOLO_MODEL}.pt'
            if cache_path.exists():
                model_path = str(cache_path)
                logger.info(f"Using cached model: {cache_path}")

        _model = YOLO(model_path)
        logger.info(f"Model loaded: {_model}")
        return True
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")
        return False

def _init_camera():
    """Initialize camera capture."""
    global _cap
    try:
        logger.info(f"Opening camera: /dev/video{CAMERA_INDEX}")
        _cap = cv2.VideoCapture(CAMERA_INDEX)
        if not _cap.isOpened():
            logger.error(f"Failed to open camera /dev/video{CAMERA_INDEX}")
            return False

        # Set camera properties for stable capture
        _cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer to avoid stale frames
        _cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        _cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        _cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)

        logger.info("Camera initialized")
        return True
    except Exception as e:
        logger.error(f"Camera init error: {e}")
        return False

def _get_latest_frame():
    """同步讀取最新相機幀（沖掉舊幀，取最新的一張）。"""
    global _cap

    if _cap is None or not _cap.isOpened():
        logger.error("Camera not initialized")
        return None

    # 沖掉緩衝區中的舊幀，只拿最新的
    frame = None
    for _ in range(5):  # 最多沖 5 次，避免無限迴圈
        ret, f = _cap.read()
        if not ret:
            break
        frame = f

    return frame if frame is not None else None

def _run_inference():
    """序列化：同時進行「讀最新幀 + GPU 推論」，用全域鎖保護避免死鎖。"""
    global _model, _latest_detections, _last_inference_time, _cap

    if _model is None:
        return {"ok": False, "error": "Model not loaded"}

    # 序列化保護：同一時刻只有一個執行緒在操作相機 + GPU
    with _state_lock:
        # 1. 讀取最新幀
        frame = _get_latest_frame()
        if frame is None:
            return {"ok": False, "error": "No frame available"}

        # 2. 在同一個鎖內進行 GPU 推論（保證無死鎖）
        try:
            t_start = time.time()
            results = _model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
            t_infer = time.time() - t_start
            _last_inference_time = t_infer

            detections = []
            if results and len(results) > 0:
                result = results[0]
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    class_name_en = result.names[class_id]
                    class_name_zh = LABELS_ZH.get(class_name_en, class_name_en)
                    confidence = float(box.conf[0])

                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    detections.append({
                        "class_id": class_id,
                        "label": class_name_en,
                        "label_zh": class_name_zh,
                        "confidence": round(confidence, 3),
                        "bbox": [x1, y1, x2, y2]
                    })

            _latest_detections = detections

            return {
                "ok": True,
                "detections": detections,
                "num_detections": len(detections),
                "inference_time_ms": round(t_infer * 1000, 2)
            }
        except Exception as e:
            logger.error(f"Inference error: {e}")
            return {"ok": False, "error": str(e)[:100]}

@app.on_event("startup")
async def startup():
    """Initialize model and camera on startup, with warmup."""
    if not _init_model():
        logger.error("Failed to initialize YOLO model")

    if not _init_camera():
        logger.error("Failed to initialize camera")

    # 工作項 2：預熱 CUDA（消耗首次 1859ms 開銷）
    logger.info("Warming up CUDA...")
    try:
        import numpy as np
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        t_start = time.time()
        _model(dummy_frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
        t_warmup = time.time() - t_start
        logger.info(f"CUDA warmup complete: {t_warmup*1000:.1f}ms")
    except Exception as e:
        logger.warning(f"Warmup failed (non-critical): {e}")

    logger.info("Perception service started (序列化設計，無背景執行緒)")

@app.get("/health")
def health():
    """Health check endpoint."""
    model_loaded = _model is not None
    camera_ok = _cap is not None and _cap.isOpened()

    return {
        "ok": model_loaded and camera_ok,
        "model": YOLO_MODEL if model_loaded else None,
        "camera": f"/dev/video{CAMERA_INDEX}" if camera_ok else None,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "latest_inference_ms": _last_inference_time * 1000 if _last_inference_time else 0
    }

@app.post("/state")
def state():
    """序列化推論：同時讀幀 + GPU 推論，無死鎖。"""
    return _run_inference()

@app.get("/frame.jpg")
def frame_jpg():
    """Return latest frame as JPEG (for debugging)."""
    with _state_lock:
        frame = _get_latest_frame()

    if frame is None:
        return {"ok": False, "error": "No frame available"}

    try:
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            return {"ok": False, "error": "JPEG encoding failed"}

        return {
            "ok": True,
            "frame_b64": base64.b64encode(buf).decode(),
            "shape": list(frame.shape)
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}
