# 視覺/感知服務相機畫面串流調查報告

## 調查摘要

**問題**：聲學前端（pathA-eval）需要相機畫面串流來疊加聲源方向指示（DoA overlay）

**調查結果**：
- ❌ **現成 MJPEG 串流**：無
- ⚠️ **單幀 JPEG 端點**：有（perception `/frame.jpg`，原始相機）
- ❌ **標註畫面（帶 YOLO 框）**：無

---

## 詳細調查

### 1. docker-compose.yml 配置

#### robotcar-perception (YOLO 物體檢測)
```yaml
perception:
  build: { context: ., dockerfile: docker/perception/Dockerfile }
  image: robotcar-perception:1.0.0
  runtime: nvidia
  ports:
    - "127.0.0.1:8001:8000"     # ← 映射到主機 8001
  devices:
    - ${VIDEO_DEV:-/dev/video0}:/dev/video0
  environment:
    - YOLO_MODEL=${YOLO_MODEL:-yolo11n}
    - CONF_THRESHOLD=${CONF_THRESHOLD:-0.5}
    - CAMERA_INDEX=${CAMERA_INDEX:-0}
    - FRAME_RATE=${FRAME_RATE:-30}
```

#### robotcar-vision (VLM 視覺語言模型)
```yaml
vision:
  build: { context: ., dockerfile: docker/vision/Dockerfile }
  image: robotcar-vision:latest
  # ← 無 ports 映射，只在 docker 網絡內可達 (http://vision:8000)
  devices:
    - ${VIDEO_DEV:-/dev/video0}:/dev/video0
  environment:
    - OLLAMA_URL=http://ollama-new:11434
    - VLM_MODEL=${VLM_MODEL:-llava}
```

**結論**：
- perception: 8001 → 8000（主機可訪問）
- vision: 內網可達（docker DNS: vision:8000）

---

### 2. 服務端點分析

#### perception 服務 (`src/perception/server.py`)

**端點 1**：`GET /health` — 服務狀態
```json
{
  "ok": true,
  "model": "yolo11n",
  "camera": "/dev/video0",
  "confidence_threshold": 0.5,
  "latest_inference_ms": 299.5
}
```

**端點 2**：`POST /state` — 執行 YOLO 推理
```json
{
  "ok": true,
  "detections": [
    {
      "class_id": 0,
      "label": "person",
      "label_zh": "人",
      "confidence": 0.93,
      "bbox": [0, 146, 104, 479]
    },
    ...
  ],
  "num_detections": 2,
  "inference_time_ms": 299.5
}
```

**端點 3**：`GET /frame.jpg` — 原始相機幀（JPEG）
```
HTTP/1.1 200 OK
Content-Type: image/jpeg
Content-Length: 82269 bytes

[JPEG 二進制數據]
```
- **驗證測試**：亮度 = 133.5 ✓ 真實相機畫面
- **特性**：
  - ✓ 是單個 JPEG 幀（不是串流）
  - ✓ 是原始相機畫面（**未標註**）
  - ✓ 沒有 YOLO 框繪製
  - ✗ 沒有 MJPEG 邊界（每次需單獨 HTTP GET）

#### vision 服務 (`src/vision/server.py`)

**端點 1**：`GET /health` — 服務狀態
```json
{
  "ok": true,
  "vlm": "llava"
}
```

**端點 2**：`POST /capture` — 視覺語言模型分析
- 輸入：prompttext
- 過程：內部讀相機 → 編碼為 JPEG base64 → 發送到 Ollama VLM
- 輸出：文字描述
- ✗ 不返回畫面，不進行流式輸出

#### webui 服務 (`src/webui/server.py`)

**端點**：`GET /api/frame` — 相機畫面代理
- 代理 perception 的 `/frame.jpg`
- 無流式功能

---

### 3. 代碼特徵搜索

#### 搜尋結果

| 關鍵字 | perception | vision | 說明 |
|--------|-----------|--------|------|
| `stream` | ❌ | ❌ (只在 OLLAMA API 中) | 無流式端點 |
| `mjpeg` | ❌ | ❌ | 無 MJPEG 實現 |
| `StreamingResponse` | ❌ | ❌ | 無 FastAPI 流式響應 |
| `multipart` | ❌ | ❌ | 無多部分邊界格式 |
| `imshow` | ❌ | ❌ | 無 OpenCV 窗口顯示 |
| `VideoWriter` | ❌ | ❌ | 無視頻文件輸出 |
| `imencode` | ✓ (1 用途) | ✓ (1 用途) | 只用於單幀 JPEG 編碼 |
| `draw` / `putText` / `rectangle` | ❌ | ❌ | **無畫框功能** |
| `annotate` | ❌ | ❌ | 無標註功能 |
| `websocket` | ❌ | ❌ | 無 WebSocket |

**結論**：兩個服務都沒有：
- 即時視頻串流（MJPEG、H.264 等）
- 畫框標註功能
- WebSocket 實時推送

---

### 4. 運作流程

```
客戶端 GET /frame.jpg
  ↓
perception 服務
  ├─ 讀取 /dev/video0 最新幀
  ├─ cv2.imencode('.jpg') → JPEG 二進制
  └─ 返回 HTTP 響應 (一次)
  
每次需要新幀 → 重新 GET /frame.jpg
```

**限制**：
- ⚠️ 非流式（每幀 1 個 HTTP 請求）
- ⚠️ 無法同步：客戶端 HTTP 往返延遲 + 服務端讀幀延遲
- ⚠️ 無標註：返回原始相機，不包含 YOLO 檢測結果

---

## 音聲前端集成可行性分析

### 方案 A：使用 perception `/frame.jpg`（最小改動）
```javascript
// 在前端定時 GET perception 的幀，疊加 DoA
setInterval(async () => {
  const img = await fetch('http://perception:8001/frame.jpg');
  // ... 畫 DoA overlay ...
}, 50); // 20fps
```

**優點**：
- ✓ 無需修改服務代碼
- ✓ 馬上可用

**缺點**：
- ⚠️ 同步困難（DoA 和相機幀可能不同步）
- ⚠️ 頻繁 HTTP 請求（網絡開銷）
- ⚠️ 延遲較高（往返 + 讀幀時間）

### 方案 B：為 perception 新增 MJPEG 流端點（推薦）
**最小修改**：在 `src/perception/server.py` 中新增一個 `/stream.mjpg` 端點

```python
from fastapi.responses import StreamingResponse

async def stream_generator():
    """MJPEG 流生成器"""
    while True:
        with _state_lock:
            frame = _get_latest_frame()
        
        if frame is None:
            continue
        
        ok, buf = cv2.imencode('.jpg', frame)
        if not ok:
            continue
        
        # MJPEG 邊界格式
        yield b'--frame\r\n'
        yield b'Content-Type: image/jpeg\r\n'
        yield b'Content-Length: ' + str(len(buf)).encode() + b'\r\n\r\n'
        yield buf.tobytes()
        yield b'\r\n'
        
        # 控制幀率 (30fps)
        await asyncio.sleep(1/30)

@app.get('/stream.mjpg')
async def stream_mjpg():
    return StreamingResponse(
        stream_generator(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )
```

**優點**：
- ✓ 真實串流（低延遲）
- ✓ 有邊界格式（HTML `<img>` 可直接使用）
- ✓ WebSocket DoA 幀與相機幀時序更接近
- ✓ 單 URL，前端簡單

**缺點**：
- ⚠️ 需修改 perception 服務（但仍屬非破壞性）
- ⚠️ 增加 perception 容器的負載（另一路 MJPEG 編碼）

### 方案 C：專設視頻聚合服務（複雜，不推薦）
- 新服務訂閱 perception `/frame.jpg`
- 聚合 perception 檢測 + 音聲 DoA + 其他數據
- 提供單一 MJPEG 輸出

**缺點**：
- ❌ 增加系統複雜性
- ❌ 多層聚合導致延遲

---

## 建議方案

### 短期（適用 pathA-eval）
使用 **perception `/frame.jpg`**（方案 A）
- 聲學前端定時 GET 最新幀
- 前端 JavaScript 疊加 DoA（Canvas overlay）
- 無需修改任何服務

### 長期（生產環境）
為 **perception 新增 `/stream.mjpg`**（方案 B）
- 修改 1 個文件：`src/perception/server.py`
- 新增 ~15 行代碼（stream_generator + 路由）
- 無需修改 docker-compose.yml 或其他服務
- 獲得真實低延遲串流

---

## 結論

| 項目 | 現況 | 可用性 |
|------|------|--------|
| **現成 MJPEG 串流** | ❌ 無 | — |
| **單幀 JPEG 端點** | ✓ 有 | ⚠️ 可用（需客戶端輪詢） |
| **標註畫面** | ❌ 無 | — |
| **推薦集成方式** | — | 方案 A（短期）或方案 B（長期） |

**下一步**：
1. 若要立即啟用音聲 + 相機疊加（pathA-eval）→ 使用方案 A（無服務改動）
2. 若要生產級品質 → 實施方案 B（新增 MJPEG 流）

---
調查時間：2026-09-02 15:50 UTC+8
調查範圍：唯讀（無任何服務改動）
