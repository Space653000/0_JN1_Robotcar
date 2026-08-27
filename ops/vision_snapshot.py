#!/usr/bin/env python3
"""
Vision Snapshot Tool — 从 perception 抓取相机帧，跑 YOLO 偵測，畫框存圖
用途：讓 Stephen 親眼看到實際的相機畫面 + 偵測結果
"""

import os
import sys
import requests
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO

# 配置
PERCEPTION_URL = "http://127.0.0.1:8001"
YOLO_MODEL = "/root/.cache/yolov8/yolo11n.pt"
OUTPUT_DIR = Path("data/vision_snapshots")
CONFIDENCE_THRESHOLD = 0.5

# 創建輸出目錄
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 載入中文標籤
LABELS_ZH = {
    "person": "人",
    "cup": "杯子",
    "bottle": "瓶子",
    "chair": "椅子",
    "table": "桌子",
    "dog": "狗",
    "cat": "貓",
    "car": "車",
    "truck": "卡車",
    "bus": "巴士",
}


def capture_frame():
    """從 perception 服務獲取當前幀（避免設備占用）"""
    try:
        resp = requests.get(f"{PERCEPTION_URL}/frame.jpg", timeout=5)
        if resp.status_code != 200:
            print(f"❌ 無法從 perception 獲取幀: {resp.status_code}")
            return None

        data = resp.json()
        if not data.get("ok"):
            print(f"❌ perception 服務錯誤: {data.get('error')}")
            return None

        # 解碼 base64 圖像
        import base64
        frame_b64 = data.get("frame_b64")
        if not frame_b64:
            print("❌ 無效的幀數據")
            return None

        frame_bytes = base64.b64decode(frame_b64)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            print("❌ 無法解碼圖像")
            return None

        return frame
    except Exception as e:
        print(f"❌ 讀取相機幀失敗: {e}")
        return None


def run_yolo_detection(frame):
    """運行 YOLO 偵測（透過 perception 服務）"""
    try:
        # 發送圖幀到 perception，讓它直接做偵測
        _, buf = cv2.imencode(".jpg", frame)
        files = {"image": ("frame.jpg", buf.tobytes(), "image/jpeg")}

        # perception /state 返回偵測結果
        resp = requests.post(f"{PERCEPTION_URL}/state", timeout=10)
        if resp.status_code != 200:
            print(f"❌ perception 偵測失敗: {resp.status_code}")
            return None

        data = resp.json()
        if not data.get("ok"):
            print(f"❌ perception 錯誤: {data.get('error')}")
            return None

        return data.get("detections", [])
    except Exception as e:
        print(f"❌ 偵測失敗: {e}")
        return None


def draw_detections(frame, detections):
    """在幀上畫出偵測框和標籤"""
    if not detections:
        return frame, []

    drawn_detections = []

    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label_en = det["label"]
        label_zh = det["label_zh"]
        confidence = det["confidence"]

        # 畫矩形框
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # 畫標籤
        label = f"{label_zh} {confidence:.2f}"
        cv2.putText(frame, label, (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        drawn_detections.append({
            "label_zh": label_zh,
            "label_en": label_en,
            "confidence": confidence
        })

    return frame, drawn_detections


def snapshot(label=""):
    """拍攝一張快照，存圖並記錄結果"""
    print(f"📸 拍攝快照（{label}）...")

    # 讀取相機幀
    frame = capture_frame()
    if frame is None:
        return None

    # 運行 YOLO 偵測
    result = run_yolo_detection(frame)

    # 畫框
    frame_with_boxes, detections = draw_detections(frame, result)

    # 生成檔名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_num = len(list(OUTPUT_DIR.glob("snap_*.jpg"))) + 1
    filename = f"snap_{snap_num:03d}_{timestamp}.jpg"
    filepath = OUTPUT_DIR / filename

    # 存圖
    cv2.imwrite(str(filepath), frame_with_boxes)
    print(f"✅ 已存圖：{filepath}")

    # 輸出結果
    if detections:
        detection_str = " + ".join([
            f"{d['label_zh']} {d['confidence']}" for d in detections
        ])
        print(f"   偵測到：{detection_str}")
    else:
        print(f"   偵測到：（無物體）")

    return {
        "filename": filename,
        "filepath": str(filepath),
        "label": label,
        "detections": detections
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        label = sys.argv[1]
    else:
        label = f"快照_{datetime.now().strftime('%H%M%S')}"

    result = snapshot(label)
    if result:
        sys.exit(0)
    else:
        sys.exit(1)
