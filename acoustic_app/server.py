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
from fastapi.responses import FileResponse
import numpy as np
from dsp import AudioCapture, DOAEstimator, SpectrumAnalyzer, compute_frame
import sys

# ============================================================================
# 配置
# ============================================================================
PORT = 8011
AUDIO_SR = 16000
AUDIO_CHANNELS = 2
AUDIO_BLOCKSIZE = 512  # ~32ms @ 16kHz
TARGET_FPS = 20  # 目标帧率

app = FastAPI(title="Jetson Acoustic DoA")

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


# ============================================================================
# 初始化
# ============================================================================
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
        "target_fps": TARGET_FPS
    }


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
    success = await init_audio()
    if not success:
        print("[FATAL] 无法初始化音频，某些功能将不可用")


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理"""
    global audio_capture
    if audio_capture:
        audio_capture.stop()
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
