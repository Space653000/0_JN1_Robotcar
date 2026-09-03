"""
XVF3800 实时声源定位 WebSocket 后端 (FastAPI)

- GET /: 返回 shell.html (統一首頁)
- GET /acoustic: 返回 index.html (聲學即時)
- GET /dashboard: 返回 jn1_dashboard.html (儀表板)
- WS /ws/live: 实时发送 FRAME_CONTRACT JSON 帧
- 绑定 0.0.0.0:8011
- HTTP Basic Auth (ACOUSTIC_USER, ACOUSTIC_PASS from .env)
"""

import asyncio
import json
import time
import base64
import secrets
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
import numpy as np
import cv2
from dsp import AudioCapture, DOAEstimator, SpectrumAnalyzer, compute_frame
import sys
import io
import httpx

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

# 方位角偏移校准（存档路径）
OFFSET_FILE = Path(__file__).parent / "azimuth_offset.txt"
AZIMUTH_OFFSET = 0.0

# 加载已保存的 offset
if OFFSET_FILE.exists():
    try:
        AZIMUTH_OFFSET = float(OFFSET_FILE.read_text().strip())
        print(f"[INIT] 已加载 AZIMUTH_OFFSET = {AZIMUTH_OFFSET}°")
    except Exception as e:
        print(f"[WARN] 无法加载 offset 文件: {e}")
        AZIMUTH_OFFSET = 0.0

app = FastAPI(title="Jetson Acoustic DoA + Camera")

# ============================================================================
# HTTP Basic Auth Middleware
# ============================================================================
AUTH_USER = os.environ.get("ACOUSTIC_USER", "")
AUTH_PASS = os.environ.get("ACOUSTIC_PASS", "")

class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 放行 WebSocket 路徑（JS 無法帶 Authorization header，瀏覽器安全政策限制）
        if request.url.path.startswith('/ws'):
            return await call_next(request)
        # fail-closed：沒有設定帳密就一律拒絕，絕不「靜默開放」
        if not (AUTH_USER and AUTH_PASS):
            return Response(
                status_code=503,
                content="伺服器未設定 ACOUSTIC_USER / ACOUSTIC_PASS，已拒絕所有請求。",
                media_type="text/plain; charset=utf-8",
            )
        auth_header = request.headers.get("Authorization", "")
        is_authenticated = False
        if auth_header.startswith("Basic "):
            try:
                credentials = base64.b64decode(auth_header[6:]).decode()
                username, _, password = credentials.partition(":")
                # 用定時安全比較，避免 timing attack
                ok_u = secrets.compare_digest(username, AUTH_USER)
                ok_p = secrets.compare_digest(password, AUTH_PASS)
                is_authenticated = ok_u and ok_p
            except Exception:
                is_authenticated = False
        if not is_authenticated:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="JN1 Acoustic"'}
            )
        return await call_next(request)

app.add_middleware(BasicAuthMiddleware)

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

# 校準緩衝（最近 ~2 秒的原始方位，用於校準）
import collections
azimuth_buffer = collections.deque(maxlen=int(2 * TARGET_FPS))  # 40 幀 @ 20fps

# 效能統計緩衝（最近 ~100 幀的計時數據）
class TimingFrame:
    def __init__(self, ts, audio_read, gcc, spectrum, frame_build, ws_send):
        self.timestamp = ts
        self.audio_read_ms = audio_read
        self.gcc_ms = gcc
        self.spectrum_ms = spectrum
        self.frame_build_ms = frame_build
        self.ws_send_ms = ws_send

timing_buffer = collections.deque(maxlen=100)  # 最近 100 幀
timing_lock = asyncio.Lock()

# 全局攝像頭對象
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
        # 打开 /dev/video0 (C922 主设备)
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

        if not cap.isOpened():
            print("[CAMERA] 错误: 无法打开 /dev/video0")
            camera_ready = False
            return False

        # 尝试设置 MJPG 编码（很多 UVC 摄像头需要）
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)

        # 设置分辨率和帧率
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # 测试读取一帧，检查亮度
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[CAMERA] 错误: 无法读取帧")
            cap.release()
            camera_ready = False
            return False

        # 计算平均亮度（灰度化 → 平均像素值）
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = np.mean(gray)
        print(f"[CAMERA] 首帧亮度: {brightness:.1f}")

        if brightness < 10:
            print("[CAMERA] 错误: 画面太黑（亮度<10），可能是全黑或摄像头开不了")
            cap.release()
            camera_ready = False
            return False

        # 成功
        camera = cap
        camera_ready = True
        print(f"[CAMERA] ✓ 已打开 /dev/video0 ({CAMERA_WIDTH}x{CAMERA_HEIGHT}@{CAMERA_FPS}fps, 亮度={brightness:.1f})")
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
async def get_shell():
    """返回主外殼（兩頁籤）"""
    shell_path = static_dir / "shell.html"
    if shell_path.exists():
        return FileResponse(shell_path, media_type="text/html")
    else:
        return {"error": "shell.html 不存在", "static_dir": str(static_dir)}


@app.get("/acoustic")
async def get_acoustic():
    """返回聲學即時頁面"""
    acoustic_path = static_dir / "index.html"
    if acoustic_path.exists():
        return FileResponse(acoustic_path, media_type="text/html")
    else:
        return {"error": "index.html 不存在", "static_dir": str(static_dir)}


@app.get("/dashboard")
async def get_dashboard():
    """返回儀表板頁面"""
    dashboard_path = Path("/home/jetson/0_JN1_Robotcar/jn1_dashboard.html")
    if dashboard_path.exists():
        return FileResponse(dashboard_path, media_type="text/html")
    else:
        return {"error": "jn1_dashboard.html 不存在", "path": str(dashboard_path)}


# ============================================================================
# 資源遙測：純讀 /proc 與 /sys，不需要安裝 jtop / psutil
# 在 3.5GB 餘裕下做決策，必須先有量測。
# ============================================================================
_cpu_prev = {"total": 0, "idle": 0}


def _read_meminfo():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k.strip()] = int(v.split()[0])  # kB
        total = info.get("MemTotal", 0) / 1048576.0        # GiB
        avail = info.get("MemAvailable", 0) / 1048576.0
        sw_t = info.get("SwapTotal", 0) / 1048576.0
        sw_f = info.get("SwapFree", 0) / 1048576.0
        return {"ram_total_gb": round(total, 2),
                "ram_avail_gb": round(avail, 2),
                "ram_used_pct": round((1 - avail / total) * 100, 1) if total else None,
                "swap_used_gb": round(sw_t - sw_f, 2)}
    except Exception:
        return {}


def _read_cpu():
    """整體 CPU 使用率（兩次取樣差分）"""
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
        vals = [int(v) for v in parts[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)
        dt = total - _cpu_prev["total"]
        di = idle - _cpu_prev["idle"]
        _cpu_prev["total"], _cpu_prev["idle"] = total, idle
        if dt <= 0:
            return None
        return round((1 - di / dt) * 100, 1)
    except Exception:
        return None


def _read_temp():
    """最高的熱區溫度（°C）"""
    import glob as _g
    best = None
    for p in _g.glob("/sys/devices/virtual/thermal/thermal_zone*/temp"):
        try:
            v = int(open(p).read().strip())
            c = v / 1000.0 if v > 1000 else float(v)
            if best is None or c > best:
                best = c
        except Exception:
            pass
    return round(best, 1) if best is not None else None


def _read_gpu():
    """Jetson GPU 負載（%）"""
    import glob as _g
    for pat in ("/sys/devices/platform/*.gpu/load",
                "/sys/devices/gpu.0/load",
                "/sys/class/devfreq/*.gpu/device/load"):
        for p in _g.glob(pat):
            try:
                return round(int(open(p).read().strip()) / 10.0, 1)
            except Exception:
                pass
    return None


def _read_disk():
    try:
        st = os.statvfs("/")
        free = st.f_bavail * st.f_frsize / (1024 ** 3)
        total = st.f_blocks * st.f_frsize / (1024 ** 3)
        return {"disk_free_gb": round(free, 1), "disk_total_gb": round(total, 1)}
    except Exception:
        return {}


@app.get("/api/telemetry")
async def telemetry():
    """系統資源即時數據（唯讀）"""
    d = {"cpu_pct": _read_cpu(), "gpu_pct": _read_gpu(), "temp_c": _read_temp()}
    d.update(_read_meminfo())
    d.update(_read_disk())
    return d


# ============================================================================
# JN1 視覺 + 助手（代理現有服務：perception :8001、brain :21500）
# ============================================================================
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://127.0.0.1:8001")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:21500")


@app.get("/vision")
async def vision_page():
    f = Path(__file__).parent / "static" / "vision.html"
    return FileResponse(str(f)) if f.exists() else Response(status_code=404, content="vision.html not found")


@app.get("/assistant")
async def assistant_page():
    f = Path(__file__).parent / "static" / "assistant.html"
    return FileResponse(str(f)) if f.exists() else Response(status_code=404, content="assistant.html not found")


@app.post("/api/vision/detect")
async def vision_detect():
    """代理 perception /state（YOLO 偵測）"""
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.post(PERCEPTION_URL + "/state")
            return r.json()
    except Exception as e:
        return {"ok": False, "error": type(e).__name__}


@app.post("/api/vision/describe")
async def vision_describe():
    """代理 brain /see（VLM 場景描述）"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(BRAIN_URL + "/see")
            return r.json()
    except Exception as e:
        return {"ok": False, "reply": "視覺服務暫時不可用。", "error": type(e).__name__}


@app.post("/api/tts/say")
async def tts_say(payload: dict):
    text = (payload or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "text 不可為空"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(TTS_URL + "/say", json={"text": text.strip()})
            return r.json()
    except Exception as e:
        return {"ok": False, "error": "無法連線 tts: " + type(e).__name__}


@app.post("/api/assistant/ask")
async def assistant_ask(payload: dict):
    """代理 brain /ask（本地先答·難題問雲端由 brain 內建處理）"""
    text = (payload or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "text 不可為空"}
    if len(text) > 2000:
        return {"ok": False, "error": "問題太長"}
    body = {"text": text.strip(), "speak": bool((payload or {}).get("speak"))}
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(BRAIN_URL + "/ask", json=body)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": "無法連線 brain: " + type(e).__name__}


@app.post("/api/assistant/see")
async def assistant_see():
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(BRAIN_URL + "/see")
            return r.json()
    except Exception as e:
        return {"ok": False, "reply": "視覺服務暫時不可用。", "error": type(e).__name__}


@app.get("/api/assistant/health")
async def assistant_health():
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(BRAIN_URL + "/health")
            return {"ok": r.status_code == 200}
    except Exception:
        return {"ok": False}


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


@app.get("/api/stats")
async def get_stats():
    """返回效能統計（最近 ~100 幀的計時中位數）"""
    if not timing_buffer:
        return {
            "fps": 0,
            "audio_read_ms": 0,
            "gcc_ms": 0,
            "spectrum_ms": 0,
            "frame_build_ms": 0,
            "ws_send_ms": 0,
            "frames": 0
        }

    frames_list = list(timing_buffer)
    n = len(frames_list)

    # 計算 FPS（最新幀的時間戳與最舊幀的時間戳之差）
    if n > 1:
        time_diff = frames_list[-1].timestamp - frames_list[0].timestamp
        fps = (n - 1) / time_diff if time_diff > 0 else 0
    else:
        fps = 0

    # 計算各階段的中位數
    def median(values):
        if not values:
            return 0
        sorted_vals = sorted(values)
        return sorted_vals[len(sorted_vals)//2]

    audio_read_ms = median([f.audio_read_ms for f in frames_list])
    gcc_ms = median([f.gcc_ms for f in frames_list])
    spectrum_ms = median([f.spectrum_ms for f in frames_list])
    frame_build_ms = median([f.frame_build_ms for f in frames_list])
    ws_send_ms = median([f.ws_send_ms for f in frames_list])

    return {
        "fps": round(fps, 2),
        "audio_read_ms": round(audio_read_ms, 1),
        "gcc_ms": round(gcc_ms, 1),
        "spectrum_ms": round(spectrum_ms, 1),
        "frame_build_ms": round(frame_build_ms, 1),
        "ws_send_ms": round(ws_send_ms, 1),
        "frames": n
    }


@app.get("/frame.jpg")
async def proxy_frame():
    """代理 perception 的相机幀（MJPEG 轮询用）"""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            r = await client.get("http://127.0.0.1:8001/frame.jpg")
            if r.status_code == 200:
                return StreamingResponse(
                    io.BytesIO(r.content),
                    media_type="image/jpeg"
                )
    except Exception as e:
        print(f"[PROXY] /frame.jpg 代理失败: {e}")
    return StreamingResponse(
        io.BytesIO(b""),
        status_code=503,
        media_type="text/plain"
    )


@app.post("/api/calibrate_front")
async def calibrate_front():
    """校准正前方（将缓冲中位数设为 offset）"""
    global AZIMUTH_OFFSET

    if len(azimuth_buffer) < 10:
        return {
            "ok": False,
            "error": f"缓冲不足 ({len(azimuth_buffer)} < 10)"
        }

    # 计算中位数
    buffer_list = list(azimuth_buffer)
    median_angle = float(np.median(buffer_list))

    # 设置 offset：使得 calibrate 时的中位数变成 0°
    AZIMUTH_OFFSET = median_angle

    # 存档
    try:
        OFFSET_FILE.write_text(str(AZIMUTH_OFFSET))
        print(f"[CALIB] AZIMUTH_OFFSET 已保存: {AZIMUTH_OFFSET}°")
    except Exception as e:
        print(f"[CALIB] 存档失败: {e}")
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "offset": AZIMUTH_OFFSET,
        "samples": len(buffer_list),
        "median": median_angle
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


CAMERA_MJPEG_DISABLED = True  # 這條會直接開 /dev/video0，與 vision/perception 搶相機


@app.get("/camera.mjpg")
async def camera_mjpeg():
    """已停用：本端點會直接開啟 /dev/video0，與 vision / perception 搶同一支 C922，
    可能導致視覺服務失效。相機畫面請改用 /frame.jpg（代理 perception，零爭用）。"""
    if CAMERA_MJPEG_DISABLED:
        return Response(
            status_code=410,
            content="此端點已停用，請改用 /frame.jpg（避免與視覺服務搶相機）。",
            media_type="text/plain; charset=utf-8",
        )
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
    """音訊處理生成器

    持續從音訊設備讀取，計算 FRAME_CONTRACT，發送給客戶端
    """
    global frame_count, frame_start_time

    if not audio_ready:
        print("[ERROR] 音訊未初始化")
        yield {"error": "Audio not ready"}
        return

    print("[STREAM] 開始音訊流...")

    # 計時統計
    timings = {'audio_read_ms': [], 'gcc_ms': [], 'spectrum_ms': [], 'frame_build_ms': [], 'ws_send_ms': []}

    try:
        while True:
            try:
                frame_start = time.perf_counter()
                t_loop_start = time.perf_counter()

                # 讀一個 block
                t_audio_start = time.perf_counter()
                audio_2ch = audio_capture.read_block()
                if audio_2ch is None:
                    print("[ERROR] 讀音訊失敗")
                    yield {"error": "Audio read failed"}
                    break
                audio_read_ms = (time.perf_counter() - t_audio_start) * 1000

                # 計算幀
                t_frame_start = time.perf_counter()
                frame = compute_frame(
                    audio_2ch,
                    sr=AUDIO_SR,
                    doa_estimator=doa_estimator,
                    spectrum_analyzer=spectrum_analyzer,
                    timestamp_ns=int(time.time_ns())
                )
                frame_build_ms = (time.perf_counter() - t_frame_start) * 1000

                if frame:
                    # 提取計時數據
                    if '_timing' in frame:
                        timings['gcc_ms'].append(frame['_timing']['gcc_ms'])
                        timings['spectrum_ms'].append(frame['_timing']['spectrum_ms'])
                        del frame['_timing']

                    timings['audio_read_ms'].append(audio_read_ms)
                    timings['frame_build_ms'].append(frame_build_ms)

                    # 記錄原始方位到緩衝（用於校準）
                    raw_azimuth = frame['azimuth']
                    azimuth_buffer.append(raw_azimuth)

                    # 應用 offset：azimuth = (raw - AZIMUTH_OFFSET + 360) % 360
                    frame['azimuth'] = int((raw_azimuth - AZIMUTH_OFFSET + 360) % 360)

                    frame_count += 1

                    t_send = time.perf_counter()
                    yield frame
                    ws_send_ms = (time.perf_counter() - t_send) * 1000
                    timings['ws_send_ms'].append(ws_send_ms)

                    # 保存到效能統計緩衝
                    try:
                        timing_buffer.append(TimingFrame(
                            ts=time.time(),
                            audio_read=audio_read_ms,
                            gcc=timings['gcc_ms'][-1] if timings['gcc_ms'] else 0,
                            spectrum=timings['spectrum_ms'][-1] if timings['spectrum_ms'] else 0,
                            frame_build=frame_build_ms,
                            ws_send=ws_send_ms
                        ))
                    except:
                        pass

                    # 每 ~5 秒印出統計
                    if frame_count % int(TARGET_FPS * 5) == 0:
                        print(f"\n[STATS @ frame {frame_count}]")
                        for key in timings:
                            if timings[key]:
                                vals = sorted(timings[key])
                                median = vals[len(vals)//2]
                                print(f"  {key}: {median:.1f}ms (median)")

                # 節流：每幀約 1/TARGET_FPS 秒（50ms @ 20fps）
                dt = (time.perf_counter() - frame_start) * 1000  # 毫秒
                sleep_time = max(0.0, (1.0 / TARGET_FPS) - (dt / 1000))
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            except Exception as frame_error:
                print(f"[FRAME_ERROR] {frame_error}", flush=True)
                continue

    except Exception as e:
        print(f"[ERROR] 流處理異常: {e}")
        yield {"error": str(e)}
    finally:
        # 計算實際 fps
        elapsed = time.time() - frame_start_time
        actual_fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"\n[STREAM] 結束，實際 FPS: {actual_fps:.1f} ({frame_count} 幀 in {elapsed:.1f}s)")

        # 最終統計
        print("[FINAL STATS]")
        for key in timings:
            if timings[key]:
                vals = sorted(timings[key])
                median = vals[len(vals)//2]
                print(f"  {key}: {median:.1f}ms (median)")


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
    # camera_ok = await init_camera()  # 禁用本地相机（由代理端点 /frame.jpg 从 perception 获取）
    if not audio_ok:
        print("[FATAL] 无法初始化音频，某些功能将不可用")
    # if not camera_ok:
    #     print("[WARN] 无法初始化摄像头，将以音频模式运行")


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
