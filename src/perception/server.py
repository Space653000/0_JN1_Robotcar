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
_latest_frame = None
_latest_detections = None
_frame_lock = Lock()
_inference_lock = Lock()
_last_inference_time = 0.0

def _init_model():
    """Initialize YOLO model."""
    global _model
    try:
        logger.info(f"Loading YOLO model: {YOLO_MODEL}")
        _model = YOLO(YOLO_MODEL)
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

def _capture_loop():
    """Background thread: continuously capture frames."""
    global _latest_frame, _cap

    if _cap is None or not _cap.isOpened():
        logger.error("Camera not initialized")
        return

    while True:
        try:
            ret, frame = _cap.read()
            if ret and frame is not None:
                with _frame_lock:
                    _latest_frame = frame.copy()
            time.sleep(1.0 / FRAME_RATE)
        except Exception as e:
            logger.error(f"Capture loop error: {e}")
            time.sleep(0.5)

def _get_frame():
    """Get the latest captured frame."""
    with _frame_lock:
        return _latest_frame.copy() if _latest_frame is not None else None

def _run_inference(frame):
    """Run YOLO inference on frame, return detected objects with Chinese labels."""
    global _model, _latest_detections, _last_inference_time

    if _model is None:
        return {"ok": False, "error": "Model not loaded"}

    if frame is None:
        return {"ok": False, "error": "No frame available"}

    try:
        with _inference_lock:
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
    """Initialize model and camera on startup."""
    if not _init_model():
        logger.error("Failed to initialize YOLO model")

    if not _init_camera():
        logger.error("Failed to initialize camera")

    # Start background capture thread
    capture_thread = Thread(target=_capture_loop, daemon=True)
    capture_thread.start()
    logger.info("Perception service started")

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
    """Run inference and return detected objects."""
    frame = _get_frame()
    return _run_inference(frame)

@app.get("/frame.jpg")
def frame_jpg():
    """Return latest frame as JPEG (for debugging)."""
    frame = _get_frame()
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
