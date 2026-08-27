"""robotcar-webui v2 — 完整代理能力展現

功能對應（自建代理路由）：
  faq_name/ability/battery/where → FAQ 快捷按鈕
  state                          → 「前面有什麼」 (看鏡頭偵測)
  ocr                            → 「唸出來」 (讀字/OCR)
  describe                       → 「仔細描述」 (VLM 詳細分析)
  depth                          → 「多遠」 (距離估算)
  referent                       → 「代詞解析」 (那是什麼)
  chat                           → 自由對話

記憶管理：
  - 8 輪對話記憶 (MEM_TURNS=8)
  - 代詞解析 (_last_objects, _last_location)
  - 防幻覺檢查 (YOLO 80 classes)
"""
import os
import io
import time
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 外部服務 URL（容器內 DNS）
BRAIN_URL = os.environ.get("BRAIN_URL", "http://brain:8000")
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://perception:8000")
ASR_URL = os.environ.get("ASR_URL", "http://asr:8000")
TTS_URL = os.environ.get("TTS_URL", "http://tts:8000")
VISION_URL = os.environ.get("VISION_URL", "http://vision:8000")

app = FastAPI(title="robotcar-webui", version="2.0.0")


class DialogMessage(BaseModel):
    """對話消息"""
    text: str


class QuickAction(BaseModel):
    """快捷功能"""
    action: str  # faq_name / state / ocr / describe / depth / referent / chat


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


@app.post("/api/quick-action")
async def quick_action(action: QuickAction):
    """快捷功能（一鍵觸發）"""
    action_map = {
        "faq_name": "你叫什麼",
        "faq_ability": "你會做什麼",
        "faq_battery": "電池剩多少",
        "faq_where": "你在哪裡",
        "state": "前面有什麼",
        "ocr": "上面寫什麼",
        "describe": "仔細描述一下",
        "depth": "這個有多遠",
        "referent": "那是什麼",
        "recall": "我剛剛說什麼",
    }

    if action.action not in action_map:
        return JSONResponse({"error": f"未知快捷功能: {action.action}"}, status_code=400)

    trigger_text = action_map[action.action]

    try:
        r = requests.post(
            f"{BRAIN_URL}/ask",
            json={"text": trigger_text},
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        return {
            "reply": data.get("reply", ""),
            "intent": data.get("intent", ""),
            "action": action.action,
            "trigger_text": trigger_text,
            "ok": data.get("ok", False),
        }
    except Exception as e:
        logger.error(f"快捷功能失敗: {e}")
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
            background-color: #0a0a0a;
            color: #e0e0e0;
            line-height: 1.5;
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
            background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
            border-bottom: 2px solid #333;
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
        }

        .header h1 {
            font-size: 18px;
            font-weight: 600;
            letter-spacing: 1px;
        }

        .status-bar {
            display: flex;
            gap: 8px;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: #444;
            transition: all 0.3s;
        }

        .status-dot.online {
            background-color: #4ade80;
            box-shadow: 0 0 6px rgba(74, 222, 128, 0.4);
        }

        /* 主內容 */
        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 10px;
            overflow-y: auto;
            overflow-x: hidden;
        }

        .section {
            background-color: #1a1a1a;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 10px;
            flex-shrink: 0;
        }

        .section-title {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #888;
            margin-bottom: 8px;
        }

        /* 相機區域 */
        .camera-container {
            width: 100%;
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

        /* 快捷按鈕 */
        .quick-buttons {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(70px, 1fr));
            gap: 6px;
            margin-bottom: 8px;
        }

        .btn-quick {
            padding: 6px 8px;
            background-color: #1e3a8a;
            color: white;
            border: 1px solid #1e40af;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
            word-break: break-word;
        }

        .btn-quick:hover {
            background-color: #1e40af;
            box-shadow: 0 0 8px rgba(30, 64, 175, 0.4);
        }

        .btn-quick:active {
            transform: scale(0.95);
        }

        .btn-quick.loading {
            opacity: 0.6;
            cursor: not-allowed;
        }

        /* 偵測結果 */
        .detections {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }

        .detection-tag {
            background-color: #0f1a2a;
            border: 1px solid #2a4a6a;
            border-radius: 12px;
            padding: 4px 8px;
            font-size: 11px;
            color: #4ade80;
        }

        /* 對話區域 */
        .dialog-section {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 200px;
        }

        .dialog-history {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 8px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 8px;
            background-color: #0f0f0f;
            border: 1px solid #222;
            border-radius: 4px;
            font-size: 12px;
        }

        .dialog-message {
            padding: 6px 8px;
            border-radius: 4px;
            max-width: 85%;
            word-wrap: break-word;
        }

        .dialog-message.user {
            align-self: flex-end;
            background-color: #1a3a1a;
            color: #4ade80;
            border-left: 2px solid #4ade80;
        }

        .dialog-message.bot {
            align-self: flex-start;
            background-color: #1a2a3a;
            color: #60a5fa;
            border-left: 2px solid #60a5fa;
        }

        .dialog-message.intent {
            align-self: center;
            font-size: 10px;
            color: #aaa;
            background-color: #2a2a2a;
            border: none;
            padding: 3px 6px;
        }

        .dialog-input-group {
            display: flex;
            gap: 6px;
        }

        .dialog-input {
            flex: 1;
            padding: 8px;
            background-color: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            color: #e0e0e0;
            font-size: 14px;
        }

        .dialog-input:focus {
            outline: none;
            border-color: #60a5fa;
            box-shadow: 0 0 4px rgba(96, 165, 250, 0.2);
        }

        .btn {
            padding: 8px 12px;
            background-color: #1e40af;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
        }

        .btn:hover {
            background-color: #1e3a8a;
        }

        .btn:active {
            transform: scale(0.95);
        }

        .btn.loading {
            opacity: 0.6;
        }

        /* 響應式 */
        @media (max-width: 640px) {
            .main {
                gap: 8px;
                padding: 8px;
            }

            .section {
                padding: 8px;
            }

            .quick-buttons {
                grid-template-columns: repeat(5, 1fr);
            }

            .camera-container {
                aspect-ratio: 16/9;
            }

            input, textarea, select {
                font-size: 16px !important;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- 頭部 -->
        <div class="header">
            <h1>🤖 JN1 機器車</h1>
            <div class="status-bar" id="statusBar"></div>
        </div>

        <!-- 主內容 -->
        <div class="main">
            <!-- 相機區域 -->
            <div class="section">
                <div class="section-title">📹 即時畫面</div>
                <div class="camera-container" id="cameraContainer">
                    <div style="color: #666; font-size: 12px;">載入中...</div>
                </div>
            </div>

            <!-- 快捷功能 -->
            <div class="section">
                <div class="section-title">⚡ 快捷功能</div>
                <div class="quick-buttons">
                    <button class="btn-quick" data-action="state" title="自動判斷是否有人/物體">前面有什麼</button>
                    <button class="btn-quick" data-action="ocr" title="OCR 讀字">唸出來</button>
                    <button class="btn-quick" data-action="describe" title="VLM 詳細分析">仔細描述</button>
                    <button class="btn-quick" data-action="faq_name" title="自我介紹">你叫什麼</button>
                    <button class="btn-quick" data-action="faq_ability" title="能力介紹">你會做什麼</button>
                    <button class="btn-quick" data-action="recall" title="記憶回想">剛剛說啥</button>
                </div>
            </div>

            <!-- 偵測結果 -->
            <div class="section">
                <div class="section-title">👁️ 偵測結果</div>
                <div class="detections" id="detections">
                    <div style="color: #666; font-size: 12px;">等待中...</div>
                </div>
            </div>

            <!-- 對話區域 -->
            <div class="section dialog-section">
                <div class="section-title">💬 對話（代理全路由）</div>
                <div class="dialog-history" id="dialogHistory"></div>
                <div class="dialog-input-group">
                    <input
                        type="text"
                        class="dialog-input"
                        id="dialogInput"
                        placeholder="輸入指令..."
                    />
                    <button class="btn" id="sendBtn">送出</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const state = {
            health: {},
            isLoading: false,
        };

        window.addEventListener('DOMContentLoaded', () => {
            initApp();
        });

        async function initApp() {
            // 事件綁定
            document.getElementById('sendBtn').addEventListener('click', sendMessage);
            document.getElementById('dialogInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });

            // 快捷按鈕
            document.querySelectorAll('.btn-quick').forEach(btn => {
                btn.addEventListener('click', () => quickAction(btn.dataset.action));
            });

            // 定時更新
            updateHealth();
            updateFrame();
            updateDetections();

            setInterval(updateHealth, 5000);
            setInterval(updateFrame, 1500);
            setInterval(updateDetections, 10000);
        }

        // 健康檢查
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
                { name: '文字', key: 'vision' },
            ];

            services.forEach(svc => {
                const isOnline = state.health[svc.key] === 'online';
                const item = document.createElement('div');
                item.className = 'status-item';

                const dot = document.createElement('div');
                dot.className = `status-dot ${isOnline ? 'online' : ''}`;

                const label = document.createElement('span');
                label.textContent = svc.name;

                item.appendChild(dot);
                item.appendChild(label);
                bar.appendChild(item);
            });
        }

        // 即時畫面
        async function updateFrame() {
            try {
                const container = document.getElementById('cameraContainer');
                const img = container.querySelector('img') || document.createElement('img');
                img.src = '/api/frame?t=' + Date.now();
                if (!container.querySelector('img')) {
                    container.innerHTML = '';
                    container.appendChild(img);
                }
            } catch (e) {
                console.error('更新畫面失敗:', e);
            }
        }

        // 偵測結果
        async function updateDetections() {
            try {
                const res = await fetch('/api/perception/state');
                const data = await res.json();

                const detections = data.detections || [];
                const container = document.getElementById('detections');
                container.innerHTML = '';

                if (detections.length === 0) {
                    container.innerHTML = '<div style="color: #666; font-size: 12px;">目前沒有偵測</div>';
                    return;
                }

                const counts = {};
                detections.forEach(det => {
                    const cls = det.label_zh || det.label || '未知';
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

        // 快捷功能
        async function quickAction(action) {
            if (state.isLoading) return;

            const btn = document.querySelector(`[data-action="${action}"]`);
            btn.classList.add('loading');
            btn.disabled = true;
            state.isLoading = true;

            try {
                const res = await fetch('/api/quick-action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action }),
                });

                const data = await res.json();
                const reply = data.reply || '(無回應)';
                const intent = data.intent || '?';

                addDialogMessage('intent', `[${intent}] ${data.trigger_text}`);
                addDialogMessage('bot', reply);
            } catch (e) {
                console.error('快捷功能失敗:', e);
                addDialogMessage('bot', '⚠️ 執行失敗');
            } finally {
                btn.classList.remove('loading');
                btn.disabled = false;
                state.isLoading = false;
            }
        }

        // 送出訊息
        async function sendMessage() {
            const input = document.getElementById('dialogInput');
            const text = input.value.trim();

            if (!text || state.isLoading) return;

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
                const intent = data.intent || '?';

                addDialogMessage('intent', `[${intent}]`);
                addDialogMessage('bot', reply);
            } catch (e) {
                console.error('對話失敗:', e);
                addDialogMessage('bot', '⚠️ 連線失敗');
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
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
