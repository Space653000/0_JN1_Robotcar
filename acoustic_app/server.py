"""
XVF3800 实时声源定位 WebSocket 后端 (FastAPI)

- GET /: 返回 static/index.html
- WS /ws/live: 实时发送 FRAME_CONTRACT JSON 帧
- 绑定 0.0.0.0:8011
"""

import asyncio
import json
import time
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import numpy as np
import cv2
from dsp import AudioCapture, DOAEstimator, SpectrumAnalyzer, compute_frame
import sys
import io

# ============================================================================
# 配置
# ============================================================================
PORT = 8011
AUDIO_SR = 16000
AUDIO_CHANNELS = 2
AUDIO_BLOCKSIZE = 512  # ~32ms @ 16kHz
TARGET_FPS = 20  # 目标帧率

# 摄像头配置
CAMERA_DEVICE = "/dev/video0"
CAMERA_HFOV_DEG = 70  # C922 水平视角
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 15

app = FastAPI(title="Jetson Acoustic DoA + Camera")

# 静态文件
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    print(f"[WARN] 静态文件目录不存在: {static_dir}")

# 全局音频对象
audio_capture = None
doa_estimator = None
spectrum_analyzer = None
audio_ready = False

# 全局摄像头对象
camera = None
camera_ready = False
camera_lock = asyncio.Lock()
latest_frame = None


# ============================================================================
# 初始化
# ============================================================================
async def init_camera():
    """初始化摄像头"""
    global camera, camera_ready

    print("[INIT] 初始化摄像头...")
    try:
        # 尝试打开摄像头（用设备号而非路径）
        # /dev/video0 对应 index 0
        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            print("[CAMERA] 错误: 无法打开设备 0")
            camera_ready = False
            return False

        # 设置分辨率和帧率
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 最小缓冲

        camera = cap
        camera_ready = True
        print(f"[CAMERA] 已打开 {CAMERA_DEVICE} ({CAMERA_WIDTH}x{CAMERA_HEIGHT}@{CAMERA_FPS}fps)")
        return True

    except Exception as e:
        print(f"[CAMERA] 错误: {e}")
        camera_ready = False
        return False


async def init_audio():
    """初始化音频捕获"""
    global audio_capture, doa_estimator, spectrum_analyzer, audio_ready

    print("[INIT] 初始化音频捕获...")
    audio_capture = AudioCapture(
        device="hw:1,0",
        sr=AUDIO_SR,
        channels=AUDIO_CHANNELS,
        blocksize=AUDIO_BLOCKSIZE
    )

    if not audio_capture.start():
        print("[ERROR] 无法启动音频捕获")
        audio_ready = False
        return False

    doa_estimator = DOAEstimator(sr=AUDIO_SR)
    spectrum_analyzer = SpectrumAnalyzer(sr=AUDIO_SR)
    audio_ready = True
    print("[INIT] 音频已准备就绪")
    return True


# ============================================================================
# HTTP 路由
# ============================================================================
@app.get("/")
async def get_index():
    """返回前端页面"""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    else:
        return {"error": "index.html 不存在", "static_dir": str(static_dir)}


@app.get("/api/status")
async def get_status():
    """返回后端状态"""
    return {
        "audio_ready": audio_ready,
        "sr": AUDIO_SR,
        "channels": AUDIO_CHANNELS,
        "target_fps": TARGET_FPS,
        "camera_ready": camera_ready,
        "camera_hfov_deg": CAMERA_HFOV_DEG
    }


@app.get("/api/config")
async def get_config():
    """返回配置"""
    return {
        "camera_hfov_deg": CAMERA_HFOV_DEG,
        "camera_width": CAMERA_WIDTH,
        "camera_height": CAMERA_HEIGHT
    }


def generate_dummy_frame():
    """生成虚拟画面（黑色+文字）"""
    frame = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=np.uint8)
    cv2.putText(frame, "Camera Offline", (150, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
    return frame


async def camera_generator():
    """摄像头 MJPEG 生成器"""
    global camera, latest_frame

    use_dummy = not camera_ready or camera is None

    if use_dummy:
        print("[CAMERA] 使用虚拟画面（硬件不可用）")

    frame_count = 0
    while True:
        try:
            if use_dummy:
                frame = generate_dummy_frame()
            else:
                ret, frame = camera.read()
                if not ret:
                    print("[CAMERA] 读取失败，切换到虚拟模式")
                    use_dummy = True
                    frame = generate_dummy_frame()

            # 保存最新帧供其他用途
            latest_frame = frame

            # 编码为 JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue

            # MJPEG 格式
            yield b'--frame\r\n'
            yield b'Content-Type: image/jpeg\r\n'
            yield b'Content-Length: ' + str(len(buffer)).encode() + b'\r\n\r\n'
            yield buffer.tobytes()
            yield b'\r\n'

            frame_count += 1
            if frame_count % 15 == 0 and use_dummy:
                # 虚拟模式下降低帧率
                await asyncio.sleep(0.1)
            elif frame_count % 5 == 0:
                await asyncio.sleep(0.01)

        except Exception as e:
            print(f"[CAMERA] 错误: {e}")
            break


@app.get("/camera.mjpg")
async def camera_mjpeg():
    """MJPEG 视频流"""
    return StreamingResponse(
        camera_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ============================================================================
# WebSocket 实时传输
# ============================================================================
frame_count = 0
frame_start_time = time.time()


async def frame_generator():
    """音频处理生成器

    持续从音频设备读取，计算 FRAME_CONTRACT，发送给客户端
    """
    global frame_count, frame_start_time

    if not audio_ready:
        print("[ERROR] 音频未初始化")
        yield {"error": "Audio not ready"}
        return

    print("[STREAM] 开始音频流...")
    block_interval = 1.0 / (AUDIO_SR / AUDIO_BLOCKSIZE / TARGET_FPS)

    try:
        while True:
            # 读一个 block
            audio_2ch = audio_capture.read_block()
            if audio_2ch is None:
                print("[ERROR] 读音频失败")
                yield {"error": "Audio read failed"}
                break

            # 计算帧
            frame = compute_frame(
                audio_2ch,
                sr=AUDIO_SR,
                doa_estimator=doa_estimator,
                spectrum_analyzer=spectrum_analyzer,
                timestamp_ns=int(time.time_ns())
            )

            if frame:
                frame_count += 1
                yield frame

            # 限制帧率
            await asyncio.sleep(block_interval * 0.9)  # 略提前以保证帧率

    except Exception as e:
        print(f"[ERROR] 流处理异常: {e}")
        yield {"error": str(e)}
    finally:
        # 计算实际 fps
        elapsed = time.time() - frame_start_time
        actual_fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"[STREAM] 结束，实际 FPS: {actual_fps:.1f} ({frame_count} 帧 in {elapsed:.1f}s)")


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点，发送实时音频帧"""
    await websocket.accept()
    print("[WS] 客户端已连接")

    global frame_count, frame_start_time
    frame_count = 0
    frame_start_time = time.time()

    try:
        async for frame in frame_generator():
            if isinstance(frame, dict) and "error" in frame:
                await websocket.send_json(frame)
                break
            else:
                # 发送 FRAME_CONTRACT JSON
                await websocket.send_json(frame)

    except WebSocketDisconnect:
        print("[WS] 客户端已断开连接")
    except Exception as e:
        print(f"[WS] 异常: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass


# ============================================================================
# Startup/Shutdown
# ============================================================================
@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    audio_ok = await init_audio()
    camera_ok = await init_camera()
    if not audio_ok:
        print("[FATAL] 无法初始化音频，某些功能将不可用")
    if not camera_ok:
        print("[WARN] 无法初始化摄像头，将以音频模式运行")


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理"""
    global audio_capture, camera
    if audio_capture:
        audio_capture.stop()
    if camera:
        camera.release()
    print("[SHUTDOWN] 后端已关闭")


# ============================================================================
# 手动启动（调试用）
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    print(f"[START] 启动服务器 http://0.0.0.0:{PORT}")
    print(f"[START] 前端: http://<jetson-ip>:{PORT}/")
    print(f"[START] WebSocket: ws://<jetson-ip>:{PORT}/ws/live")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
