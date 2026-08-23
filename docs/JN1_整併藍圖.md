# JN1 四專案整併藍圖

**建檔日期**：2026-08-23  
**更新時間**：實時盤點  
**範圍**：JN1_AI、JN1_OPENCLAW、JN1_ROLE、JN1_ROS2 → 0_JN1_Robotcar  

---

## 一、四專案總覽表

| 專案 | 用途定位 | 核心資產 | 運行狀態 | 技術債 | 建議狀態 |
|---|---|---|---|---|---|
| **JN1_AI** | 完整 AI 大腦系統；語音/視覺/思考核心 | BRAIN(COGNITION/MEMORY/GOVERNANCE)、SENSES(耳朵/眼睛)、ACTUATORS(嘴巴)、ZMQ 通訊、TensorRT YOLO、Whisper GPU、內存管理、事件總線 | ✅ 可運行，docker-compose 配置完善；Whisper/TTS/YOLO 實測有效 | 多版本 main（v7~v11 並存）、實驗代碼雜亂、寫死的 ALSA 配置、未整理的 LABS 目錄 | 作為**大腦核心**直接遷移；清理版本分支 |
| **JN1_OPENCLAW** | 智慧體框架；多技能路由與 agent 執行 | Agent 框架(`run_agent.py`)、技能橋接、Ollama 集成、WebTool/OfficeTools/MediaTools、使命控制隊列 | ❌ 架構不清晰；包含大量複製自 JN1_AI 的重複代碼；venv 環境未確認 | 嚴重代碼重複、skills_bridge 臃腫、無清晰的模組邊界、文檔缺失 | 參考智慧體框架設計；**核心概念**納入新 Brain；重複代碼刪除 |
| **JN1_ROLE** | 角色引擎與對話個性化；視覺描述 | 角色配置（Jarvis/Past-Self/Exhibition-Agent）、YOLO + 中文標籤映射、記憶纖維（memory_fabric）、多角色狀態管理、音頻庫、TTS 集成 | ⚠️ 部分可運行；Jarvis_core 實現完整但版本多（v2.8~v3.5）；視覺模組未完全集成 | 多版本並存、vision.py 半成品、角色配置與代碼分離不清、舊數據堆積 | 提取**角色管理**與**視覺檢測**邏輯；YOLO 標籤映射可直接複用 |
| **JN1_ROS2** | ROS 2 機器人底盤與移動控制橋接 | jn1_ros_bridge.py（ROS 通訊骨架）、Docker 支持 | ❌ 最小化；未完成；test_brain_move.py 是半成品 | 骨架不全、缺少實際移動指令實現、無测试覆蓋 | 文件保存以備未來；暫不優先整併 |

---

## 二、四專案資料夾架構樹狀圖

### 2.1 JN1_AI 架構

```
JN1_AI/
├── BRAIN/                         # 智能核心引擎
│   ├── COGNITION/                 # 認知層：任務分解、工具路由、推理控制
│   │   ├── auto_scholar.py
│   │   ├── concept_engine.py
│   │   ├── reasoning_controller.py
│   │   ├── task_decomposer.py
│   │   └── tool_router.py
│   ├── DATABANK/                  # 數據倉庫：狀態管理、記憶糾正
│   │   ├── CORRECTIONS/
│   │   ├── INTERNAL_DB/
│   │   ├── LIBRARY/
│   │   ├── LOGS/
│   │   └── correction_manager.py
│   ├── GOVERNANCE/                # 治理層：行為守衛、政策審計
│   │   ├── behavior_guard.py
│   │   ├── governance_kernel.py
│   │   ├── policy_auditor.py
│   │   ├── policy_dsl.py
│   │   └── policy_matrix.json
│   ├── MEMORY/                    # 內存系統：短期/長期/向量記憶
│   │   ├── long_term_memory.py
│   │   ├── memory_index.py
│   │   ├── short_term_memory.py
│   │   ├── vector_memory.py
│   │   └── library_builder.py
│   ├── MODEL_ROUTER/              # 模型路由：SLA、推理選擇
│   │   ├── router_core.py
│   │   ├── routing_policy.py
│   │   └── sla_router.py
│   ├── LLM_gateway.py
│   ├── EVENT_bus.py
│   ├── MEMORY_system.py
│   ├── POLICY_engine.py
│   ├── persona.py
│   └── reflex.py
├── SENSES/                        # 感知層
│   ├── ears_process.py            # 麥克風進程管理
│   ├── ears_wake.py               # 喚醒詞檢測
│   ├── ears_whisper.py            # Whisper GPU ASR
│   └── eyes_tensorrt.py           # TensorRT YOLO 視覺檢測
├── ACTUATORS/                     # 動作層
│   ├── mouth.py                   # TTS 發音
│   ├── mouth_process.py
│   └── stock_controller.py        # 庫存控制（示例）
├── COMM/                          # 通訊層
│   ├── zmq_bus.py                 # ZMQ 發佈/訂閱
│   └── zmq_subscriber.py
├── SYSTEM/                        # 系統監控
│   ├── supervisor.py
│   ├── metrics_collector.py
│   ├── audit_logger.py
│   ├── system_state_registry.py
│   └── power_manager.py
├── CORE/                          # 核心進程
│   └── brain_process.py
├── LABS/                          # 實驗室（測試代碼）
│   ├── VOICE_LAB/
│   └── STOCK_LAB/
├── models/                        # 本地模型快取
│   ├── whisper-base/              # ~142MB
│   ├── whisper-base-gpu/          # ~142MB
│   ├── paraphrase-multilingual-MiniLM-L12-v2/  # ~466MB (語義搜尋)
│   └── tts/                       # 語音合成模型
├── main.py                        # 主入口（最新版本）
├── main_v7~v11.py                 # 舊版本（應清理）
├── docker-compose.yaml
├── Dockerfile
└── code.env                       # ⚠️ 機密檔案（唯讀）
```

### 2.2 JN1_OPENCLAW 架構

```
JN1_OPENCLAW/
├── agent_framework/               # 智慧體框架
│   ├── core/
│   │   ├── agent.py               # Agent 核心邏輯
│   │   ├── agent_test.py
│   │   └── prompts.py
│   ├── tools/
│   │   ├── search_tools.py
│   │   ├── web_tools.py
│   │   ├── office_tools.py
│   │   ├── media_tools.py
│   │   ├── finance_tools.py
│   │   └── code_tools.py
│   ├── mission_control/           # 任務佇列
│   │   ├── incoming/              # 待執行任務
│   │   └── outbox/                # 完成結果
│   ├── skills_bridge/             # ⚠️ 包含大量 JN1_AI 複製代碼（應刪除）
│   │   └── [太多重複的 BRAIN、SENSES、SYSTEM 代碼]
│   └── venv/
├── core/
│   ├── agent.py
│   ├── agent_test.py
│   └── __init__.py
├── bin/
│   └── ollama                     # ollama 執行檔
├── run_agent.py                   # 智慧體啟動器
├── Backstage_openclaw.sh
└── backstage.log
```

### 2.3 JN1_ROLE 架構

```
JN1_ROLE/
├── app/                           # 主應用層
│   ├── jarvis_core.py             # Jarvis 角色核心（v2.6~v3.5）
│   ├── role_engine.py             # 角色引擎
│   ├── memory_fabric.py           # 記憶管理
│   ├── action_layer.py            # 行動層
│   ├── jn1_audio_lib.py           # 音頻庫（自製）
│   ├── jn1_config.py              # 配置管理
│   ├── utils.py
│   └── chat.py
├── brain/                         # 大腦模組
│   ├── jn1_brain_v28.py           # 多任務大腦 v2.8
│   ├── jn1_multitask_brain.py     # 多任務大腦
│   └── jn1_eye_engine.py          # 眼睛引擎（視覺）
├── perception/                    # 感知層
│   └── video/
│       ├── jn1_vision.py          # YOLO + 中文標籤
│       ├── jn1_vision_daemon.py   # 視覺守護進程
│       └── tts/                   # TTS 執行檔
├── roles.yaml                     # 角色配置檔
├── docker-compose.yml
├── Dockerfile.jn1
├── asound.conf
├── BACKUP/                        # 備份（舊代碼）
├── OLD_DATA/                      # 歷史數據
├── logs/
│   ├── system.log
│   └── vision.log
├── memory/
│   └── vectors/
├── runs/                          # YOLO 推論結果
└── RUN_JARVIS_V3.5.sh
```

### 2.4 JN1_ROS2 架構

```
JN1_ROS2/
├── src/                           # ROS 2 源代碼（空）
├── jn1_ros_bridge.py              # ROS 橋接骨架
├── test_brain_move.py             # 測試（半成品）
├── orin_amr_docker/               # Docker 支持（複製自外部）
│   ├── run_docker.sh
│   └── README.md
└── Dockerfile.jn1
```

---

## 三、去蕪存菁清單

### 3.1 **直接複用** ✅

| 資產 | 來源 | 目標位置 | 說明 |
|---|---|---|---|
| BRAIN.COGNITION | JN1_AI | `src/brain/cognition/` | 任務分解、推理、工具路由；保持原設計 |
| BRAIN.MEMORY | JN1_AI | `src/brain/memory/` | 短期/長期/向量記憶；核心資產 |
| BRAIN.GOVERNANCE | JN1_AI | `src/brain/governance/` | 行為守衛、政策審計；安全關鍵 |
| SENSES.ears_whisper | JN1_AI | `src/asr/` | GPU Whisper 實現；已驗證有效 |
| SENSES.eyes_tensorrt | JN1_AI | `src/vision/detection/` | TensorRT YOLO；高效檢測 |
| ACTUATORS.mouth | JN1_AI | `src/tts/` | TTS 基礎（補完 Kokoro 實現） |
| COMM.zmq_bus | JN1_AI | `src/infra/messaging/` | 進程間通訊；保持原設計 |
| YOLO 中文標籤映射 | JN1_ROLE | `src/vision/labels/zh_CN.json` | LABEL_MAP（人、椅子、貓...） |
| 角色配置架構 | JN1_ROLE | `config/roles/` | roles.yaml 格式；多角色支持 |

### 3.2 **參考重寫** 🔄

| 資產 | 來源 | 目標 | 原因 |
|---|---|---|---|
| Agent 框架 | JN1_OPENCLAW | 新 `src/brain/agent/` | 去除 skills_bridge 重複代碼；統一使用 0_JN1_Robotcar 的微服務模式 |
| 視覺描述流程 | JN1_ROLE + JN1_AI | 新 `src/vision/vlm_pipeline.py` | 合併 YOLO 檢測 + VLM 描述 + OpenCC 中文轉換 |
| 大腦主迴圈 | JN1_ROLE（jarvis_core） | 擴充 `src/brain/server.py` | 移入對話狀態管理、記憶存取；去掉 edge-tts 改用 Kokoro |
| ROS 橋接 | JN1_ROS2 | `src/infra/ros_bridge/` (未來) | 完成 test_brain_move.py；集成底盤控制 |

### 3.3 **捨棄** ❌

| 資產 | 來源 | 理由 |
|---|---|---|
| main_v7 ~ v10.py | JN1_AI | 舊版本；已由 main.py 取代 |
| JN1_OPENCLAW/skills_bridge/ | JN1_OPENCLAW | 100% 複製自 JN1_AI；應刪除 |
| JN1_OPENCLAW/venv/ | JN1_OPENCLAW | Python 虛擬環境；已改用 Docker |
| JN1_ROLE/OLD_DATA/ | JN1_ROLE | 歷史檔案；無生產價值 |
| JN1_ROLE/runs/ | JN1_ROLE | YOLO 實驗結果；自動產生 |
| LABS/ 下的實驗代碼 | JN1_AI | 未完成的測試；應歸檔或刪除 |
| edge-tts 依賴 | JN1_ROLE | 已被 Kokoro 取代；移除 |

---

## 四、建議的統一資料夾架構（未來 0_JN1_Robotcar）

```
0_JN1_Robotcar/
├── src/                           # 應用層
│   ├── brain/
│   │   ├── server.py              # FastAPI 對外介面
│   │   ├── cognition/             # [直接複用] JN1_AI.COGNITION
│   │   │   ├── task_decomposer.py
│   │   │   ├── reasoning_controller.py
│   │   │   ├── tool_router.py
│   │   │   └── concept_engine.py
│   │   ├── memory/                # [直接複用] JN1_AI.MEMORY
│   │   │   ├── short_term_memory.py
│   │   │   ├── long_term_memory.py
│   │   │   ├── vector_memory.py
│   │   │   └── memory_index.py
│   │   ├── governance/            # [直接複用] JN1_AI.GOVERNANCE
│   │   │   ├── behavior_guard.py
│   │   │   ├── policy_auditor.py
│   │   │   └── policy_matrix.json
│   │   ├── agent/                 # [新增] 智慧體框架（參考 OPENCLAW）
│   │   │   ├── core.py
│   │   │   ├── tools.py
│   │   │   └── mission_control.py
│   │   ├── dialog_governor.py     # 對話管理
│   │   ├── llm_gateway.py         # LLM 閘道
│   │   └── event_bus.py           # 事件總線
│   ├── asr/
│   │   ├── server.py              # 已有；保留
│   │   └── [已完成]
│   ├── tts/
│   │   ├── server.py              # 已有；補完 Kokoro 實現
│   │   └── [升級中]
│   ├── vision/
│   │   ├── server.py              # 已有；擴充
│   │   ├── detection/             # [直接複用] JN1_AI.eyes_tensorrt
│   │   │   ├── yolo_engine.py
│   │   │   └── yolo_model.engine
│   │   ├── vlm_pipeline.py        # [新增] YOLO + VLM + 中文轉換
│   │   ├── labels/
│   │   │   ├── zh_CN.json         # [直接複用] JN1_ROLE.LABEL_MAP
│   │   │   └── coco_labels.json
│   │   └── [升級中]
│   ├── depth/
│   │   ├── server.py              # 已有
│   │   └── [按需啟動]
│   ├── ocr/
│   │   ├── server.py              # 已有
│   │   └── [按需啟動]
│   └── infra/
│       ├── messaging/             # [直接複用] JN1_AI.COMM
│       │   ├── zmq_bus.py
│       │   └── zmq_subscriber.py
│       ├── supervisor.py          # [直接複用] JN1_AI.SYSTEM
│       ├── metrics_collector.py
│       ├── audit_logger.py
│       └── ros_bridge.py          # [未來] ROS 2 集成
├── config/
│   ├── roles/
│   │   ├── roles.yaml             # [直接複用] JN1_ROLE.roles.yaml
│   │   └── role_prompts.json      # 角色提示詞
│   ├── policies/
│   │   └── policy_matrix.json     # [直接複用] JN1_AI.GOVERNANCE
│   └── models/
│       └── model_registry.json    # 模型清單
├── docker/                        # 已有；擴充新服務
│   ├── brain/
│   │   └── Dockerfile            # [新增] 完整大腦服務鏡像
│   ├── [asr/tts/vision/...]       # 已有
├── docker-compose.yml             # 已有；加入新服務
├── data/
│   ├── models/                    # 本地模型快取
│   │   ├── whisper/
│   │   ├── llm/
│   │   ├── vlm/
│   │   ├── yolo/
│   │   └── embeddings/
│   ├── logs/
│   ├── memory/                    # 持久化記憶（向量、索引）
│   └── roles/                     # 角色狀態檔
├── docs/
│   ├── ARCHITECTURE.md            # 架構文檔
│   ├── JN1_整併藍圖.md             # 本檔案
│   └── API.md
├── ops/
│   └── [健檢、回滾、部署]
└── [其他已有檔案]
```

---

## 五、中文視覺卡關的解法建議

### 現狀分析

**問題**：`vision/server.py` 中的 VLM（llava/moondream）輸出英文描述，需要翻譯成繁體中文。

**當前臨時方案**（已在 0_JN1_Robotcar 實施）：
- 使用 `opencc` 轉換英文 → 繁體中文（有局限，只能轉簡中→繁中）
- 例：`"A cat on the desk"` → `"A cat on the desk"`（OpenCC 無法翻譯英文）

### 三個完整解法

#### **解法 A：英文 VLM + LLM 翻譯樞紐** ✅ 推薦

**步驟**：
1. VLM（llava）生成英文描述
2. 呼叫 qwen2.5:3b LLM，prompt：`"將以下英文轉為繁體中文，簡潔一句話：{英文描述}"`
3. 返回繁體中文輸出

**優點**：
- 利用現有模型（llava 已拉，qwen 已拉）
- 翻譯準確度高（LLM 理解語境）
- 支援複雜場景描述

**缺點**：
- 延遲 ~2~3 秒（需要喚醒 qwen）
- VRAM 需要同時載 VLM + LLM（可用 `OLLAMA_KEEP_ALIVE` 控制卸載)

**實現**：
```python
# src/vision/vlm_pipeline.py
def describe_scene_zh(image_b64: str) -> str:
    # 1. VLM 描述
    vlm_desc = ollama_vlm_chat(VLM_MODEL, image_b64, "Describe this scene briefly.")
    
    # 2. LLM 翻譯
    llm_prompt = f"Translate to Traditional Chinese (one sentence): {vlm_desc}"
    zh_desc = ollama_llm_chat(LLM_MODEL, llm_prompt)
    
    return zh_desc
```

#### **解法 B：YOLO 檢測 + 中文標籤 + 語言模型描述**

**步驟**：
1. 用 TensorRT YOLO 檢測物件
2. 對應中文標籤（來自 JN1_ROLE）
3. 用 LLM 根據檢測結果生成自然中文描述

**優點**：
- 不需 VLM VRAM（只需 YOLO + LLM）
- 延遲短（~1 秒）
- 中文輸出原生

**缺點**：
- 只能列舉物件，難以描述場景細節、動作、顏色等
- 依賴 YOLO 檢測精度

**實現**：
```python
# JN1_AI.eyes_tensorrt + JN1_ROLE.vision
def describe_with_detection(frame) -> str:
    detections = yolo_model.predict(frame)  # [{"label": "人", "conf": 0.9}, ...]
    obj_str = ", ".join([d["label"] for d in detections])
    
    prompt = f"用繁體中文一句話描述這個場景，其中包含：{obj_str}"
    return ollama_llm_chat(LLM_MODEL, prompt)
```

#### **解法 C：遠端中文 VLM API** 🚀 未來方向

使用專業中文 VLM（需聯網），如：
- **Qwen-VL**（阿里；0.5B ~ 7B）
- **InternVL**（旷视；高精度）
- **GLM-4V**（清華智譜；多模態）
- **Baichuan-3-Vision**（百川）

**優點**：
- 原生中文輸出
- 描述品質更高

**缺點**：
- 需聯網
- API 成本
- Jetson 上難以本地運行大模型

---

### 建議優先順序

| 優先級 | 方案 | 時機 | 成本 |
|---|---|---|---|
| **1（立即）** | **A（翻譯樞紐）** | 下個 sprint；利用現有模型 | 低；+2~3 秒延遲 |
| **2（1 個月）** | **B（檢測+標籤）** | 若 A 延遲無法接受 | 中；需 YOLO TRT 優化 |
| **3（3 個月+）** | **C（中文 VLM）** | 若預算允許；外包或 API | 高；聯網依賴 |

---

## 六、遷移計劃（分期實施）

### Phase 1：基礎整合（1~2 週）

- [ ] 複製 JN1_AI 的 BRAIN、SENSES 到 `src/` 下
- [ ] 清理版本檔（刪 main_v7~v10.py）
- [ ] 搭建 `src/brain/server.py` FastAPI 主框架
- [ ] 集成 MEMORY + GOVERNANCE 模組
- [ ] 實施**解法 A**（英文 VLM + LLM 翻譯）

### Phase 2：角色 + 檢測強化（2~4 週）

- [ ] 遷移 JN1_ROLE 的 roles.yaml + 角色提示詞
- [ ] 集成 TensorRT YOLO（來自 JN1_AI）+ 中文標籤（來自 JN1_ROLE）
- [ ] 實現**解法 B** 作為備選方案
- [ ] 測試多角色對話狀態管理

### Phase 3：智慧體框架（4~6 週）

- [ ] 設計清晰的 Agent 框架（去除 OPENCLAW 的重複代碼）
- [ ] 實現 tool_router 與 mission_control
- [ ] 集成 Ollama 多模型路由（LLM + VLM + 檢測）

### Phase 4：ROS 2 與移動（6+ 週）

- [ ] 完成 jn1_ros_bridge.py；測試移動指令
- [ ] 集成底盤控制與視覺回饋迴圈
- [ ] 端到端測試

### 清理任務（並行）

- [ ] 刪除 JN1_OPENCLAW/skills_bridge/（代碼重複）
- [ ] 歸檔 JN1_AI/LABS/；留下關鍵實驗代碼
- [ ] 整理 JN1_ROLE/OLD_DATA/、JN1_ROLE/runs/

---

## 七、唯讀確認聲明

本盤點過程中，**四個舊資料夾全程唯讀**，未做任何修改：

✅ `/home/jetson/JN1_AI` — 未變更  
✅ `/home/jetson/JN1_OPENCLAW` — 未變更  
✅ `/home/jetson/JN1_ROLE` — 未變更  
✅ `/home/jetson/JN1_ROS2` — 未變更  

**機密檔案未訪問**：
- `code.env` 未讀取（已標記為禁止）

**生成物位置**：
- 本檔案：`/home/jetson/0_JN1_Robotcar/docs/JN1_整併藍圖.md`

---

## 附錄 A：核心資產遷移檢查清單

```
[ ] BRAIN/COGNITION
    [ ] task_decomposer.py → src/brain/cognition/
    [ ] reasoning_controller.py → src/brain/cognition/
    [ ] tool_router.py → src/brain/cognition/
    [ ] concept_engine.py → src/brain/cognition/

[ ] BRAIN/MEMORY
    [ ] short_term_memory.py → src/brain/memory/
    [ ] long_term_memory.py → src/brain/memory/
    [ ] vector_memory.py → src/brain/memory/
    [ ] memory_index.py → src/brain/memory/

[ ] BRAIN/GOVERNANCE
    [ ] behavior_guard.py → src/brain/governance/
    [ ] policy_auditor.py → src/brain/governance/
    [ ] policy_matrix.json → config/policies/

[ ] SENSES
    [ ] ears_whisper.py → src/asr/ (驗證已有)
    [ ] eyes_tensorrt.py → src/vision/detection/

[ ] COMM
    [ ] zmq_bus.py → src/infra/messaging/
    [ ] zmq_subscriber.py → src/infra/messaging/

[ ] Models
    [ ] whisper-base/ → data/models/whisper/
    [ ] paraphrase-multilingual-MiniLM-L12-v2/ → data/models/embeddings/
    [ ] tts/* → data/models/tts/

[ ] JN1_ROLE Assets
    [ ] roles.yaml → config/roles/
    [ ] LABEL_MAP → src/vision/labels/zh_CN.json
    [ ] memory_fabric.py → src/brain/memory/ (參考重寫)

[ ] JN1_OPENCLAW
    [ ] Agent framework 概念 → src/brain/agent/ (新設計)
```

---

## 附錄 B：中文視覺驗收標準

**預期行為**（實施解法 A 後）：

1. **拍照**：`bash bin/see.sh`
2. **VLM 描述**（英文）：`"A cat sitting on a blue chair in a bright room"`（~1 秒）
3. **LLM 翻譯**：`"一隻貓坐在亮藍色椅子上，房間很明亮"`（~2 秒）
4. **語音播放**（繁體中文）：Kokoro 讀出中文描述（~1 秒）

**總延遲目標**：≤ 4 秒（使用者可接受）

**驗收指標**：
- ✅ 中文輸出無誤（繁體、無簡字）
- ✅ 語句自然流暢
- ✅ 複雜場景描述準確（不只是物件列舉）
- ✅ 延遲 ≤ 5 秒

---

**文檔版本**：v1.0  
**最後更新**：2026-08-23  
**維護人**：JN1 系統集成團隊
