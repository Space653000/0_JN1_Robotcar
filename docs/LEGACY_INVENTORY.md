# Legacy 專案盤點報告

**產出日期**：2026-08-23
**目的**：盤點三個舊專案（JN1_AI、JN1_OPENCLAW、JN1_ROS2），評估與目前 0_JN1_Robotcar（Voice AI + Vision AI）的關聯，供資產搬遷/重寫決策參考。
**唯讀聲明**：本次盤點僅使用 `ls` / `find` / `cat` 讀取三個舊資料夾，**未對其做任何新增、修改、移動或刪除**。

---

## 1. JN1_AI（`/home/jetson/JN1_AI`）

### 用途
第一代「類人腦」語音/視覺 AI 助理系統，採 Docker 容器化部署（`jn1_ai:imperial_pulse_seeker`），host network + privileged 模式，直通 ReSpeaker 4-Mic 麥克風陣列、攝影機與 GPU。命名體系模擬人體結構：`BRAIN`（大腦）、`SENSES`（感官：耳/眼）、`ACTUATORS`（動作：嘴）、`COMM`（ZMQ 神經傳導）、`MEMORY`（記憶）、`CORE`（主流程進程）。

### 資產清單
| 模組 | 內容 | 可用性 |
|---|---|---|
| `BRAIN/` | `EVENT_bus.py`、`persona.py`、`dialog_governance.py`、`reflex.py`、`MEMORY_system.py`、`LLM_gateway.py`、`POLICY_engine.py`；子目錄 `COGNITION`（任務分解、知識圖譜、工具路由、推理控制器）、`MODEL_ROUTER`（多模型路由/SLA）、`GOVERNANCE`（行為守護、政策 DSL）| 架構完整，具參考價值 |
| `SENSES/` | `ears_whisper.py`（GPU Whisper STT）、`ears_wake.py`（喚醒詞）、`ears_process.py`、`eyes_tensorrt.py`（TensorRT 視覺推論）| 語音/視覺前處理管線，高度可複用 |
| `ACTUATORS/` | `mouth.py` / `mouth_process.py`（TTS 輸出）、`stock_controller.py` | TTS 出口封裝 |
| `COMM/` | `zmq_bus.py`、`zmq_subscriber.py` | 模組間 ZMQ 訊息匯流排，與 JN1_ROS2 對接的關鍵協定 |
| `MODELS/` | `VISION_ZOO`、`VOICE_ZOO`、`BRAIN_ZOO`（含 `llama3-8b-instruct.gguf`、`phi3-mini-4k.gguf`）| 本地 LLM/視覺/語音模型庫 |
| `LABS/` | `VOICE_LAB`（`voice_ai_ears.py` 語音實驗）、`VISION_LAB`、`STOCK_LAB`（股票查詢技能）| 實驗性技能，部分可重構為 skill |
| `SKILLS/` | `tool_process.py`、`knowledge_worker.py`、`ingest_books.py`、`TOOLS/toolbox.py` | 工具呼叫框架 |
| `code.env` | 內含 OpenWeather / Alpha Vantage / NewsAPI 等第三方 API Key | ⚠️ 含機密資訊，若複用需重新產生/輪替金鑰，不可原樣搬移 |
| `docker-compose.yaml` | GPU 直通、host network、ReSpeaker PulseAudio 掛載範本 | 音訊/GPU 容器化設定極具參考價值 |

### 架構重點
- ZMQ pub/sub 作為模組間神經傳導匯流排（`tcp://127.0.0.1:5555`），`BRAIN` 發布 `ACTION.*` 指令，`SENSES`/`ACTUATORS` 訂閱。此協定與 JN1_ROS2 的橋接器完全對應。
- `docker-compose.yaml` 展示了 Jetson 上 GPU + 音訊裝置直通的實戰設定（PulseAudio cookie、ReSpeaker 指定 source、`/dev/bus/usb` 掛載），是 Robotcar 語音/視覺容器化的直接參考範本。
- 專案內累積大量歷史快照檔（`000_JN1_AI_Full_Context_*.txt`，582KB）、`BACKUP/` 備份版本、`__pycache__`，顯示長期迭代但缺乏版本控管（`.git` 存在但混雜大量暫存產物）。

### 目前狀態
最後修改時間 2026-05-16，屬於已完成一輪開發、目前擱置的狀態；模組數量多但耦合度高，命名風格與 Robotcar 的通用工程慣例不同。

---

## 2. JN1_OPENCLAW（`/home/jetson/JN1_OPENCLAW`）

### 用途
第二代專案，聚焦「Agent 執行層」（Hands / 物理任務落地），實作一個可執行檔案操作、股票分析、文件產出（Word/Excel/PDF）等任務的本地 Agent 框架，搭配 Ollama 本地 LLM（`ollama.tar.zst` 約 1.3GB 打包映像）。

### 資產清單
| 模組 | 內容 | 可用性 |
|---|---|---|
| `core/agent.py`（24KB）| Agent 主邏輯、`prompts.py` | 核心 Agent 迴圈，具重構參考價值 |
| `agent_framework/` | `run_agent.py`、`mission_control/`（任務佇列 incoming/archive）、內含另一份 `skills_bridge`（含大量 JN1_AI 舊檔案的殘留副本，如 `code.env`、`yolov8n.onnx/pt`、`main_v7.py`）| 任務調度框架；內部殘留檔案顯示與 JN1_AI 曾共用程式碼 |
| `skills_bridge/` | `stock_app.py`、`stock_controller.py`、`stock_core.py`、`health_monitor.py` | 股票技能模組（與 JN1_AI 的 STOCK_LAB 同源） |
| `sandbox/` | `inbox` / `outbox`（按日期分資料夾）/ `workspace`，Agent 任務輸入輸出隔離區 | 任務沙箱模式可參考 |
| `security/firewall.sh` | 簡易防火牆腳本 | 待評估是否適用 Robotcar |
| `Tasks_Hands_openclaw.py`（5.4KB）| 「物理執行層」：依賴自動安裝（pandas/yfinance/matplotlib/docx）、透過 `sitecustomize.py` 動態修補 exec 以防止 Agent 產生語法錯誤程式碼 | 具巧思但屬 hack 手法，不建議直接複用，可參考其防禦思路 |
| `venv/`、`ollama.tar.zst` | 完整 Python venv 與 Ollama 映像打包 | 體積龐大（1.3GB+），不建議搬移，重新建置更乾淨 |

### 架構重點
- Agent 以檔案佇列（`mission_control/incoming` → `archive`）驅動任務，`sandbox` 提供輸入輸出隔離，這種「檔案驅動任務隊列」模式可作為 Robotcar 未來擴充非即時任務（如報表產出）的雛型。
- 大量防禦性 patch（暴力壓制警告、動態修補 `exec`）反映該專案在陽春試錯期間對 LLM 產生程式碼不穩定的因應方式，工程debt較重。

### 目前狀態
最後修改 2026-05-16，與 JN1_AI 同期收尾；`skills_bridge` 內殘留 JN1_AI 檔案顯示兩專案曾互相複製程式碼而非共用模組，技術債較高。

---

## 3. JN1_ROS2（`/home/jetson/JN1_ROS2`）

### 用途
預留給移動平台（AMR）對接的 ROS2 橋接層，體積最小、最單純，核心是把 JN1_AI 的「大腦」ZMQ 指令轉換成 ROS2 `/cmd_vel`（`geometry_msgs/Twist`）指令。

### 資產清單
| 檔案 | 內容 | 可用性 |
|---|---|---|
| `jn1_ros_bridge.py` | ROS2 Node，訂閱 ZMQ `tcp://127.0.0.1:5555` 的 `ACTION.MOVE` topic，解析 `linear_x` / `angular_z` JSON payload，轉發為 `Twist` 訊息發布到 `/cmd_vel` | **可直接複用**，是 ZMQ↔ROS2 橋接的完整最小實作 |
| `test_brain_move.py` | 模擬大腦端發送 ZMQ 指令的測試腳本 | 可直接作為整合測試範本 |
| `Dockerfile.jn1` | 基於 `tzushiancavedu/orinnano_amr:r36.3.0_rev1`，修正 ROS2 金鑰、安裝 `python3-zmq`、燒入橋接腳本 | 容器化 ROS2 環境的可用範本 |
| `orin_amr_docker/` | 內嵌自身 `.git` 子模組（AMR 廠商提供的 docker 啟動腳本 `run_docker.sh`）| 第三方 AMR 廠商工具，需保留原樣 |
| `00000_auto_test.sh` | 用 tmux 雙視窗（左：啟動 Docker + ROS2 橋接；右：發送測試指令）驗證流程 | 測試自動化腳本，可參考 |
| `src/` | 空目錄 | 尚未開發 |

### 架構重點
- 通訊協定明確：`ACTION.MOVE {"linear_x": float, "angular_z": float}` 字串前綴 topic + JSON payload，經 ZMQ PUB/SUB 傳遞，這正是 JN1_AI `COMM/zmq_bus.py` 的下游消費端。
- 整個專案就是一座「橋」，邏輯簡單、依賴少（`rclpy`、`zmq`），是三個舊專案中最乾淨、最適合直接搬遷或重寫沿用的部分。

### 目前狀態
最後修改 2026-04-18，開發到最小可行橋接即停止，`src/` 尚未展開，屬於「預留但未深入」狀態。

---

## 4. 與目前 Robotcar（Voice AI + Vision AI）的關聯

Robotcar 目前架構（`bin/`、`docker/`、`ops/`、`src/`、`docker-compose.yml` 等）是全新規劃的專案骨架，尚未包含具體的語音/視覺/移動邏輯。三個舊專案剛好覆蓋 Robotcar 需要的三塊拼圖：

- **語音/視覺感知與大腦決策** → JN1_AI（`SENSES`、`BRAIN`、`ACTUATORS`、`COMM`）
- **任務執行/技能擴充（Agent 化操作）** → JN1_OPENCLAW（`core/agent.py`、`sandbox` 任務隊列模式）
- **移動平台指令下發** → JN1_ROS2（ZMQ↔ROS2 橋接）

三者共用同一套 ZMQ 訊息匯流排協定（`ACTION.*` topic + JSON payload），代表這是舊系統中唯一經過驗證、可跨專案復用的「介面約定」。

## 5. 建議

### 直接複用（低風險、高投報）
- **`jn1_ros_bridge.py` + `test_brain_move.py`**（JN1_ROS2）：程式碼乾淨、依賴少，可直接搬進 Robotcar 作為移動平台橋接的起點。
- **`docker-compose.yaml` 的 GPU/音訊直通設定**（JN1_AI）：ReSpeaker PulseAudio、GPU device 掛載的寫法已驗證可行，可作為 Robotcar `docker-compose.yml` 的音訊/視覺容器範本片段。
- **ZMQ pub/sub 協定設計**（`COMM/zmq_bus.py` 概念）：作為 Robotcar 內部模組間通訊的介面約定基礎。

### 參考重寫（有價值但需重構）
- **`SENSES/ears_whisper.py`、`eyes_tensorrt.py`**（JN1_AI）：GPU Whisper STT 與 TensorRT 視覺推論的整合邏輯值得參考，但建議重寫以符合 Robotcar 現有 `src/` 架構與命名慣例，避免搬入 `BACKUP/`、`__pycache__` 等雜訊。
- **`BRAIN/COGNITION`、`MODEL_ROUTER`、`GOVERNANCE`**（JN1_AI）：多模型路由與行為守護的設計思路可參考，但模組間耦合度高，建議依 Robotcar 實際需求重新設計介面。
- **Agent 任務隊列模式**（`agent_framework/mission_control`，JN1_OPENCLAW）：檔案驅動的 inbox/outbox 任務隔離模式可參考用於非即時任務，但核心 `core/agent.py` 建議重寫，避免沿用其暴力 exec patch 等 hack 手法。

### 不建議複用
- **`ollama.tar.zst`（1.3GB 打包映像）、`venv/`**（JN1_OPENCLAW）：體積龐大且環境依賴已過時，重新建置更乾淨。
- **`code.env` 內的 API Key**（JN1_AI、及其在 `agent_framework/skills_bridge` 的殘留副本）：機密資訊不應搬移，若需相同服務應重新申請/輪替金鑰。
- **`Tasks_Hands_openclaw.py` 的動態修補 `exec` 手法**：屬於針對特定 LLM 不穩定行為的臨時 hack，技術債重，不建議沿用其實作方式。
- **各專案內的 `BACKUP/`、`__pycache__`、歷史快照 txt（如 `000_JN1_AI_Full_Context_*.txt`）**：純歷史雜訊，無需搬移。

---

## 6. 唯讀確認聲明

本次盤點過程中，對以下三個資料夾僅執行 `ls` / `find` / `cat` 讀取操作：
- `/home/jetson/JN1_AI`
- `/home/jetson/JN1_OPENCLAW`
- `/home/jetson/JN1_ROS2`

**未進行任何檔案的新增、修改、移動、刪除或權限變更，三個資料夾內容與盤點前完全一致。**
