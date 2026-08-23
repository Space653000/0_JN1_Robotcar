# JN1 Robotcar — 完整架構規劃（執行依據）

> **版本**：v1.0 ｜ **日期**：2026-08-23 ｜ **狀態**：定稿，作為所有後續執行的唯一依據
> **工作區**：`/home/jetson/0_JN1_Robotcar`（所有規劃、程式碼、檢查、產出）
> **硬體**：NVIDIA Jetson Orin NX 16GB (J4012)，L4T R36.4.7 / JetPack 6.2 / CUDA 12.6 / ROS2 Humble

---

## 一、目標與對標

### 終極目標
打造自主的 JN1 機器人車，**功能對標並超越 Hiwonder ROSOrin Pro**，並具備**遠強於原廠的 Voice AI 與 Vision AI**。

### 對標分析 — ROSOrin Pro vs JN1 Robotcar

| 能力 | ROSOrin Pro（原廠） | JN1 Robotcar（我們的目標） | 差異策略 |
|------|--------------------|--------------------------|---------|
| 運算平台 | 可選 Jetson Orin NX 16GB | **Jetson Orin NX 16GB** ✅ | 同級，站在同一起跑線 |
| Voice | 喚醒詞 + 線上/離線語音互動 | **Kokoro TTS + Whisper ASR + 多輪對話 + 代詞解析 + FAQ + 情感** | **超越**：自然對話夥伴，非命令機 |
| Vision | YOLO26 物件偵測 + 姿態 + KCF 追蹤 | **YOLO11n TRT + OCR + 單目/立體深度 + VLM 場景描述** | **超越**：能「看懂並用自然語言描述」 |
| LLM | 多模態 LLM（ChatGPT/Gemini/Grok/Llama） | **本地 Ollama VLM + 意圖路由（隱私、離線）** | 本地優先，不依賴雲端 |
| Agent 框架 | OpenClaw | **複用 JN1_OPENCLAW（inbox/outbox）概念** | 舊資產直接對接 |
| 底盤 | Mecanum 全向輪 | Mecanum / RK-六輪（外購編碼器） | 移動階段再定 |
| LiDAR | COIN-D6 360° TOF | STL27L（規劃）或同級 | 移動階段採購 |
| 深度相機 | 3D 深度相機 | RealSense D435i（規劃）+ 軟體單目深度過渡 | 軟體先行 |
| 導航 | SLAM + 路徑規劃 + 避障 | Nav2 + SLAM（複用 JN1_ROS2 橋接） | 移動階段 |
| 機械臂 | 6DOF（400g，±2mm） | 選配，未列入前三優先 | 未來擴充 |

### 核心差異化
原廠強在**移動與硬體整合**；我們的殺手鐧是**Voice AI 與 Vision AI 的智能深度** —— 這正是完成順序把兩者排在移動之前的原因。

---

## 二、架構決策（已釘死）

### 決策 1：通訊架構 = 混合式（HTTP REST 主體 + ZMQ 橋接給 ROS2）
- **主體**：所有 AI 服務走 **HTTP REST**（FastAPI + docker-compose），已驗證全綠、curl 易測、易 debug。
- **移動橋接**：第三優先才加一層 **HTTP→ZMQ 轉接**，讓舊專案 `jn1_ros_bridge.py`（ZMQ→/cmd_vel）原封不動複用。
- **理由**：Voice/Vision（前兩優先）完全不需要 ZMQ；先用現成可用的架構全速推進，不打掉重練。

### 決策 2：記憶體策略 = 常駐輕量 + 重模型 on-demand
- 16GB 為 CPU/GPU 共用，常駐控制在 **2.5–3GB**。
- 重模型（VLM、Depth）**用時才載入**，`OLLAMA_KEEP_ALIVE=30s`、`OLLAMA_MAX_LOADED_MODELS=1`（一次一個大模型）。

### 決策 3：無 torch 常駐路徑
- 常駐服務（ASR/TTS/Brain）一律 ONNX/CPU，**不進 torch**，保護記憶體預算。
- torch 只在 on-demand GPU 模組（Depth、未來 VLM 微調）出現。

### 決策 4：相機單一擁有者
- `/dev/video0` 由 perception 服務獨佔，其他模組（OCR/Depth）向 perception 取幀（`/frame.jpg`），杜絕 EBUSY。

### 決策 5：服務隔離部署
- 所有 `docker compose build/up` 一律加 `--no-deps`，單一服務失敗不級聯拖垮其他。

### 決策 6：舊資產複用原則
| 舊資產 | 處置 | 用途 |
|--------|------|------|
| JN1_AI：GPU+ReSpeaker 音訊直通 docker 設定 | **直接複用** | ReSpeaker 麥克風陣列整合 |
| JN1_AI：TensorRT 模型庫 | **直接複用** | YOLO/Vision TRT 加速 |
| JN1_ROS2：`jn1_ros_bridge.py` | **直接複用**（移動階段） | ZMQ→/cmd_vel |
| JN1_OPENCLAW：inbox/outbox 任務模式 | **參考概念** | Agent 任務佇列（技術債重，不整包搬） |
| 任何 `code.env` / API Key | **禁止搬移** | 機密 |
| 三個舊資料夾 | **唯讀** | 只讀不改不移 |

---

## 三、完成順序（不可調換）

```
第一優先 ▶ Voice AI   （自然對話弄熟）
第二優先 ▶ Vision AI  （看懂並描述）
第三優先 ▶ 移動 + ROS （複用 JN1_ROS2）
```

---

## 四、系統架構圖

```
┌───────────────────────────────────────────────────────────┐
│           手機/平板 Web UI（第三優先後期）                 │
│   即時視頻 · 語音輸入輸出 · 狀態面板                        │
└───────────────────────┬───────────────────────────────────┘
                        │ WiFi
┌───────────────────────▼───────────────────────────────────┐
│              J4012 Jetson Orin NX 16GB                      │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  第一優先：Voice AI 層（HTTP REST，常駐）           │  │
│  │   ASR  :8003  Whisper（→ SenseVoice 若可）          │  │
│  │   TTS  :8004  Kokoro（→ piper 後備）✅              │  │
│  │   Brain:21500 Ollama 意圖路由 + 8轉記憶 + FAQ       │  │
│  │           + 代詞解析 + 情感回應                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  第二優先：Vision AI 層（HTTP REST + on-demand GPU）│  │
│  │   Perception:8001 YOLO11n TRT（相機單一擁有者）     │  │
│  │   OCR       :8002 PaddleOCR（on-demand）            │  │
│  │   Depth     :8005 Depth Anything V2（on-demand）    │  │
│  │   VLM 場景描述 via Brain（YOLO輸出→自然語言）       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  第三優先：移動層（HTTP→ZMQ→ROS2）                  │  │
│  │   HTTP→ZMQ 轉接（新寫，薄層）                       │  │
│  │   jn1_ros_bridge.py（複用 JN1_ROS2）ZMQ→/cmd_vel   │  │
│  │   Nav2 + SLAM + 編碼器里程計                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  Docker Compose：ollama · asr · tts · brain ·             │
│                  perception · ocr* · depth*（*on-demand） │
└───────────────────────┬───────────────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │  底盤（第三優先）  │ Mecanum/RK-六輪 + 外購編碼器
              │  周邊：ReSpeaker · C922 · D435i · STL27L LiDAR │
              └────────────────────┘
```

---

## 五、第一優先 — Voice AI（詳細）

### 5.1 現況（已驗證 ✅）
| 服務 | 引擎 | 記憶體 | 埠 | 狀態 |
|------|------|--------|-----|------|
| TTS | Kokoro ONNX（→ piper 後備） | 279 MB | 8004 | ✅ played:true |
| ASR | Faster-Whisper（→ 無後備） | 925 MB | 8003 | ✅ 自動降級（SenseVoice 需 torch，違預算） |
| Brain | Ollama + 意圖路由 + 8轉記憶 | ~300 MB | 21500 | ✅ /ask, /talk, intent |

### 5.2 深化工作（進行中）
1. **Brain FAQ 庫**：身份問答（你叫什麼→JN1、你會什麼、電池、位置）。
2. **代詞解析**：記憶 `last_objects` / `last_location`，「那是什麼」回查上文。
3. **TTS 自然度**：標點→停頓（，0.3s／。0.5s／？0.4s），非一口氣念完。
4. **ASR 熱詞修正**：JN1、Kokoro、Jetson 等後處理修正。
5. **情感回應**：偵測語氣 → 調整回應風格（進階）。
6. **8 轉對話流測試**：身份→環境→代詞→記憶用戶名→回憶，全程連貫。

### 5.3 ReSpeaker 升級（複用 JN1_AI 資產）
- 搬入 JN1_AI 已驗證的 **ReSpeaker 音訊直通 docker 設定** → 麥克風陣列 + 波束成形 + 遠場收音。
- 取代目前單一 pulse source，提升吵雜環境辨識率。

### 5.4 驗證閘門 G-Voice
- G-V1：FAQ 準確（身份問答正確）
- G-V2：代詞解析成功（跨輪指涉）
- G-V3：TTS 停頓自然（人耳確認）
- G-V4：ASR 熱詞準確度 ≥ 85%
- G-V5：8 轉記憶連貫（回憶用戶名）

---

## 六、第二優先 — Vision AI（詳細）

### 6.1 Perception（實時感知）— 對標 YOLO26
- **模型**：YOLO11n → **TensorRT 引擎（on-device 編譯）**，複用 JN1_AI TRT 模型庫經驗。
- **輸入**：C922 `/dev/video0`（單一擁有者），提供 `/frame.jpg` 給下游。
- **輸出**：bbox / class / confidence，延遲 < 100ms。
- **埠**：8001。

### 6.2 OCR（文字識別）
- **模型**：PaddleOCR PP-OCRv4/v5（中文），CPU，on-demand。
- **不用 VLM 做 OCR**（VLM OCR 看似對常出錯）。
- **埠**：8002。

### 6.3 Depth（深度）
- **軟體過渡**：Depth Anything V2 Small（單目相對深度，非公尺），GPU on-demand。
- **硬體到位後**：RealSense D435i（真實立體深度，公尺級）。
- **埠**：8005。

### 6.4 VLM 場景描述（Vision × Voice 橋接）
- YOLO 偵測 → Brain 生成自然語言 → TTS 播放。
- 範例：`「我看到一個人坐在桌前，桌上有杯子」`。
- 這是**超越 ROSOrin Pro** 的關鍵：不只偵測，而是「看懂並用人話描述」。

### 6.5 驗證閘門 G-Vision
- G-Vi1：YOLO TRT 引擎編譯成功、`/detect` 回 bbox
- G-Vi2：OCR 讀中文標誌正確
- G-Vi3：Depth 回左/中/右相對距離
- G-Vi4：VLM 場景描述自然、經 TTS 播放
- G-Vi5：相機單一擁有者無 EBUSY 衝突

---

## 七、第三優先 — 移動 + ROS（詳細）

### 7.1 複用策略
- **薄層新寫**：HTTP `/move` 端點 → ZMQ 發佈移動指令。
- **直接複用**：`jn1_ros_bridge.py`（JN1_ROS2）訂閱 ZMQ → 發 `/cmd_vel`。
- **零基礎補完**：編碼器讀取（GPIO）→ `/odom`，由 Claude Code 自動生成 ROS2 node。

### 7.2 導航棧
- SLAM 建圖（Cartographer / slam_toolbox）。
- Nav2 路徑規劃 + 避障（吃 LiDAR + 里程計 + 深度）。
- 底盤：Mecanum（全向，對標原廠）或 RK-六輪 + 外購編碼器（成本考量）。

### 7.3 驗證閘門 G-Move
- G-M1：HTTP→ZMQ→/cmd_vel 貫通（模擬）
- G-M2：編碼器 → /odom 里程計誤差 < 5%
- G-M3：SLAM 建圖成功
- G-M4：Nav2 自主導航到點 + 避障

---

## 八、記憶體預算（16GB 共用）

```
常駐上限 2.5–3 GB：
├─ ASR (Whisper)        925 MB
├─ TTS (Kokoro)         279 MB
├─ Brain (Ollama常駐)   ~300 MB
├─ Perception (YOLO TRT) 200–400 MB
└─ OS + 安全邊際        ~1 GB

On-demand（用時載入，用完卸載）：
├─ VLM (Ollama)         視模型，一次一個
├─ Depth Anything V2    GPU
└─ OCR (PaddleOCR)      CPU ~200 MB
```

---

## 九、硬體採購路線（對標 ROSOrin Pro，軟體完成後）

| 階段 | 硬體 | 目的 | 時機 |
|------|------|------|------|
| 已有 | Jetson Orin NX 16GB, C922 | 運算 + 視覺 | ✅ |
| 語音強化 | ReSpeaker 麥克風陣列 | 遠場收音 | 第一優先中 |
| 深度 | RealSense D435i | 立體深度（取代單目） | 第二優先後 |
| 移動 | Mecanum/RK-六輪 + 編碼器 | 底盤 + 里程計 | 第三優先 |
| 導航 | STL27L 或同級 360° LiDAR | SLAM 建圖 | 第三優先 |
| 擴充 | 6DOF 機械臂（選配） | 抓取（對標原廠） | 未來 |

> 採購決策：軟體完成前先留紀錄，不急著買（沿用既定方針）。robotkingdom.com.tw 為採購來源。

---

## 十、里程碑與整體驗證閘門

| 里程碑 | 內容 | 閘門 | 狀態 |
|--------|------|------|------|
| M1 | 基礎服務骨架（HTTP REST + docker） | G1 | ✅ |
| M2a | Voice 引擎（TTS/ASR/Brain） | G1–G4 | ✅ |
| **M2b** | **Voice AI 深化（FAQ/代詞/自然度/ReSpeaker）** | **G-Voice** | 🔨 進行中 |
| M3 | Vision AI（YOLO TRT + OCR + Depth + VLM描述） | G-Vision | ⏳ 次階段 |
| M4 | 移動 + ROS（複用 JN1_ROS2 + Nav2） | G-Move | 📋 規劃 |
| M5 | 手機/平板 Web UI 整合 | — | 📋 規劃 |

---

## 十一、執行紀律（所有階段適用）

1. **一次性完成**，終端側工作跑到底，不逐步要確認。
2. **自動修復**：requirements 衝突、語法、邏輯錯誤自行修正，失敗自動降級（不中斷）。
3. **三次自驗證**：修改 → 建置 → 執行，三次綠燈才 PASS。
4. **中文報告**：每階段結果記錄到 `UPGRADE_LOG.md`。
5. **服務隔離**：`--no-deps`，失敗不級聯。
6. **舊資料夾唯讀**：JN1_AI / JN1_OPENCLAW / JN1_ROS2 只讀不改。
7. **機密不搬**：API Key / code.env 一律留在原處。

---

## 十二、下一步（立即）

**完成 M2b — Voice AI 深化**：Brain FAQ + 代詞解析、TTS 自然度、ASR 熱詞、8 轉對話流測試，並評估搬入 JN1_AI 的 ReSpeaker 音訊直通設定。通過 G-Voice 五道閘門後，進入 M3 Vision AI。
