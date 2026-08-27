"""robotcar-webui — 手機/平板區網控制介面

功能：
- 即時相機畫面
- 視覺偵測結果
- 打字對話
- 服務狀態監控

架構：WebUI 在容器內代理外部服務（brain、perception），前端只連 webui 一個入口
"""
import os
import io
import time
import requests
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 外部服務 URL（容器內DNS）
BRAIN_URL = os.environ.get("BRAIN_URL", "http://brain:8000")
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://perception:8000")
ASR_URL = os.environ.get("ASR_URL", "http://asr:8000")
TTS_URL = os.environ.get("TTS_URL", "http://tts:8000")
VISION_URL = os.environ.get("VISION_URL", "http://vision:8000")

app = FastAPI(title="robotcar-webui", version="1.0.0")


class DialogMessage(BaseModel):
    """對話消息"""
    text: str


# ============================================================================
# API：代理外部服務
# ============================================================================

@app.get("/api/health")
async def health_check():
    """檢查各服務健康狀態"""
    services = {
        "brain": BRAIN_URL,
        "perception": PERCEPTION_URL,
        "asr": ASR_URL,
        "tts": TTS_URL,
        "vision": VISION_URL,
    }

    status = {}
    for name, url in services.items():
        try:
            r = requests.get(f"{url}/health", timeout=2)
            status[name] = "online" if r.status_code == 200 else "offline"
        except:
            status[name] = "offline"

    return status


@app.get("/api/frame")
async def get_frame():
    """取得即時相機畫面（JPEG）"""
    try:
        r = requests.get(f"{PERCEPTION_URL}/frame.jpg", timeout=5)
        r.raise_for_status()
        return StreamingResponse(
            io.BytesIO(r.content),
            media_type="image/jpeg"
        )
    except Exception as e:
        logger.error(f"獲取畫面失敗: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/perception/state")
async def get_perception_state():
    """取得當前視覺偵測結果"""
    try:
        r = requests.post(f"{PERCEPTION_URL}/state", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        logger.error(f"獲取偵測結果失敗: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ask")
async def ask_brain(msg: DialogMessage):
    """向大腦提問（代理 brain /ask）"""
    try:
        r = requests.post(
            f"{BRAIN_URL}/ask",
            json={"text": msg.text},
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        return {
            "reply": data.get("reply", ""),
            "intent": data.get("intent", ""),
            "ok": data.get("ok", False),
        }
    except Exception as e:
        logger.error(f"大腦回應失敗: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================================
# 前端HTML（單頁應用）
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JN1 機器車控制介面</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'PingFang TC', sans-serif;
            background-color: #1a1a1a;
            color: #e0e0e0;
            line-height: 1.5;
            padding: 0;
        }

        .container {
            max-width: 100%;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* 頭部 */
        .header {
            background: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
            border-bottom: 2px solid #333;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
        }

        .header h1 {
            font-size: 20px;
            font-weight: 600;
            letter-spacing: 1px;
        }

        .status-bar {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background-color: #444;
            transition: background-color 0.3s;
        }

        .status-dot.online {
            background-color: #4ade80;
            box-shadow: 0 0 8px rgba(74, 222, 128, 0.5);
        }

        .status-label {
            font-size: 12px;
            color: #aaa;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* 主內容 */
        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 12px;
            padding: 12px;
            overflow-y: auto;
            overflow-x: hidden;
        }

        /* 即時畫面區塊 */
        .section {
            background-color: #0a0a0a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 12px;
            flex-shrink: 0;
        }

        .section-title {
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #aaa;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .camera-container {
            width: 100%;
            max-width: 100%;
            aspect-ratio: 4/3;
            background: #000;
            border: 1px solid #222;
            border-radius: 4px;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .camera-container img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }

        .camera-loading {
            color: #666;
            font-size: 12px;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
        }

        /* 偵測結果 */
        .detections {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
            gap: 8px;
        }

        .detection-tag {
            background-color: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 6px 8px;
            font-size: 11px;
            text-align: center;
            color: #4ade80;
            word-break: break-word;
        }

        /* 對話框 */
        .dialog-section {
            display: flex;
            flex-direction: column;
            max-height: 300px;
        }

        .dialog-history {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 8px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 8px;
            background-color: #000;
            border-radius: 4px;
            border: 1px solid #222;
            font-size: 12px;
        }

        .dialog-message {
            padding: 6px 8px;
            border-radius: 4px;
            max-width: 90%;
            word-wrap: break-word;
        }

        .dialog-message.user {
            align-self: flex-end;
            background-color: #1e4620;
            color: #4ade80;
            border-left: 2px solid #4ade80;
        }

        .dialog-message.bot {
            align-self: flex-start;
            background-color: #1a2a3a;
            color: #60a5fa;
            border-left: 2px solid #60a5fa;
        }

        .dialog-input-group {
            display: flex;
            gap: 6px;
        }

        .dialog-input {
            flex: 1;
            padding: 8px 10px;
            background-color: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            color: #e0e0e0;
            font-size: 14px;
            font-family: inherit;
        }

        .dialog-input:focus {
            outline: none;
            border-color: #60a5fa;
            box-shadow: 0 0 4px rgba(96, 165, 250, 0.3);
        }

        .btn {
            padding: 8px 14px;
            background-color: #1e40af;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }

        .btn:hover {
            background-color: #1e3a8a;
        }

        .btn:active {
            transform: scale(0.95);
        }

        .btn-secondary {
            background-color: #374151;
        }

        .btn-secondary:hover {
            background-color: #4b5563;
        }

        .loading-spinner {
            display: inline-block;
            width: 12px;
            height: 12px;
            border: 2px solid #333;
            border-top: 2px solid #60a5fa;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* 響應式設計 */
        @media (max-width: 768px) {
            .header h1 {
                font-size: 16px;
            }

            .main {
                gap: 10px;
                padding: 10px;
            }

            .section {
                padding: 10px;
            }

            .camera-container {
                aspect-ratio: 16/9;
            }

            .dialog-history {
                max-height: 200px;
            }
        }

        /* 防止 iOS 自動放大 */
        input, textarea, select {
            font-size: 16px !important;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- 頭部 -->
        <div class="header">
            <h1>🤖 JN1 機器車</h1>
            <div class="status-bar" id="statusBar">
                <!-- 動態填充 -->
            </div>
        </div>

        <!-- 主內容 -->
        <div class="main">
            <!-- 即時畫面 -->
            <div class="section">
                <div class="section-title">
                    📹 即時畫面
                    <span style="font-size: 10px; color: #666;">每秒更新</span>
                </div>
                <div class="camera-container" id="cameraContainer">
                    <div class="camera-loading">載入中...</div>
                </div>
            </div>

            <!-- 偵測結果 -->
            <div class="section">
                <div class="section-title">
                    👁️ 偵測結果
                    <button class="btn btn-secondary" id="refreshDetectionsBtn" style="padding: 4px 8px; font-size: 11px;">重新掃描</button>
                </div>
                <div class="detections" id="detections">
                    <div style="color: #666; font-size: 12px;">等待中...</div>
                </div>
            </div>

            <!-- 對話 -->
            <div class="section dialog-section">
                <div class="section-title">💬 對話</div>
                <div class="dialog-history" id="dialogHistory"></div>
                <div class="dialog-input-group">
                    <input
                        type="text"
                        class="dialog-input"
                        id="dialogInput"
                        placeholder="輸入指令..."
                        @keyup.enter="sendMessage"
                    />
                    <button class="btn" id="sendBtn">送出</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // 全域狀態
        const state = {
            health: {},
            dialogHistory: [],
            isLoading: false,
        };

        // 初始化
        window.addEventListener('DOMContentLoaded', () => {
            initApp();
        });

        async function initApp() {
            console.log('初始化 WebUI...');

            // 綁定事件
            document.getElementById('sendBtn').addEventListener('click', sendMessage);
            document.getElementById('dialogInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });
            document.getElementById('refreshDetectionsBtn').addEventListener('click', updateDetections);

            // 定時更新
            updateHealth();
            updateFrame();
            updateDetections();

            setInterval(updateHealth, 5000);
            setInterval(updateFrame, 1500);
            setInterval(updateDetections, 10000);
        }

        // 更新健康狀態
        async function updateHealth() {
            try {
                const res = await fetch('/api/health');
                const data = await res.json();
                state.health = data;
                renderStatusBar();
            } catch (e) {
                console.error('健康檢查失敗:', e);
            }
        }

        function renderStatusBar() {
            const bar = document.getElementById('statusBar');
            bar.innerHTML = '';

            const services = [
                { name: '語音', key: 'asr' },
                { name: '視覺', key: 'perception' },
                { name: '大腦', key: 'brain' },
            ];

            services.forEach(svc => {
                const isOnline = state.health[svc.key] === 'online';
                const dot = document.createElement('div');
                dot.className = `status-dot ${isOnline ? 'online' : ''}`;
                dot.title = `${svc.name}: ${isOnline ? '線上' : '離線'}`;

                const label = document.createElement('span');
                label.className = 'status-label';
                label.textContent = svc.name;

                const container = document.createElement('div');
                container.style.display = 'flex';
                container.style.alignItems = 'center';
                container.style.gap = '4px';
                container.appendChild(dot);
                container.appendChild(label);

                bar.appendChild(container);
            });
        }

        // 更新相機畫面
        async function updateFrame() {
            try {
                const container = document.getElementById('cameraContainer');
                const img = container.querySelector('img') || document.createElement('img');
                img.src = '/api/frame?t=' + Date.now(); // 防快取
                if (!container.querySelector('img')) {
                    container.innerHTML = '';
                    container.appendChild(img);
                }
            } catch (e) {
                console.error('更新畫面失敗:', e);
            }
        }

        // 更新偵測結果
        async function updateDetections() {
            try {
                const res = await fetch('/api/perception/state');
                const data = await res.json();

                const detections = data.detections || [];
                const container = document.getElementById('detections');
                container.innerHTML = '';

                if (detections.length === 0) {
                    container.innerHTML = '<div style="color: #666; font-size: 12px;">目前沒有偵測到物體</div>';
                    return;
                }

                // 去重並計數
                const counts = {};
                detections.forEach(det => {
                    const cls = det.class || '未知';
                    counts[cls] = (counts[cls] || 0) + 1;
                });

                Object.entries(counts).forEach(([cls, count]) => {
                    const tag = document.createElement('div');
                    tag.className = 'detection-tag';
                    tag.textContent = count > 1 ? `${cls}×${count}` : cls;
                    container.appendChild(tag);
                });
            } catch (e) {
                console.error('更新偵測失敗:', e);
            }
        }

        // 送出訊息
        async function sendMessage() {
            const input = document.getElementById('dialogInput');
            const text = input.value.trim();

            if (!text || state.isLoading) return;

            // 顯示使用者訊息
            addDialogMessage('user', text);
            input.value = '';

            state.isLoading = true;
            document.getElementById('sendBtn').disabled = true;

            try {
                const res = await fetch('/api/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text }),
                });

                const data = await res.json();
                const reply = data.reply || '(無回應)';
                addDialogMessage('bot', reply);
            } catch (e) {
                console.error('對話失敗:', e);
                addDialogMessage('bot', '⚠️ 連線失敗，請重試');
            } finally {
                state.isLoading = false;
                document.getElementById('sendBtn').disabled = false;
                input.focus();
            }
        }

        function addDialogMessage(role, text) {
            const history = document.getElementById('dialogHistory');
            const msg = document.createElement('div');
            msg.className = `dialog-message ${role}`;
            msg.textContent = text;
            history.appendChild(msg);
            history.scrollTop = history.scrollHeight;
        }

        // 頁面卸載時通知
        window.addEventListener('beforeunload', () => {
            console.log('WebUI 關閉');
        });
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """主頁（單頁應用）"""
    return HTML_TEMPLATE


@app.get("/health")
async def webui_health():
    """WebUI 自身健康檢查"""
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
