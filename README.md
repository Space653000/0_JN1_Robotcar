# robotcar — Milestone 1: 感知 + 思考 + 語音大腦(不含移動)

獨立 Docker Compose stack,跑在 J4012 上。完全獨立於既有 JN1(自己的資料夾、自己的 ollama、自己的模型)。
成果:**按鍵觸發語音問答**(說話→轉文字→LLM→用喇叭講出來)+ **「看看前面」視覺**(拍一張→VLM 描述→中文講出來),全中文。

## 服務
| 服務 | 影像/base | 對外 | GPU | 做什麼 |
|---|---|---|---|---|
| `ollama-new` | `dustynv/ollama:0.6.8-r36.4-cu126-22.04` | 內部 only | 是 | 本地 LLM(`qwen2.5:3b`)+ VLM(`llava`) |
| `asr` | python3.10 + faster-whisper(CPU) | 內部 only | 否 | 從麥克風錄音→中文轉錄 |
| `tts` | python3.10 + piper `zh_CN-huayan`(CPU) | 內部 only | 否 | 中文合成→經 PulseAudio 播(藍芽喇叭)+ 存 wav |
| `vision` | python3.10 + opencv | 內部 only | 否 | 抓 `/dev/video0` 一張→呼叫 llava |
| `brain` | python3.10 | **`127.0.0.1:21500`** | 否 | 串起 mic→LLM→TTS、camera→VLM→中文→TTS |

服務間一律走 Compose 服務名(`http://asr:8000` 等),**不走 127.0.0.1**。只有 `brain` 對主機開一個 port(綁 127.0.0.1)。

## 部署(在 PC 上跑 rsync,其餘在 Jetson 上)— 這就是首發 runbook

> 前置:`ssh j4012` 免密碼可用;`/home/jetson/projects/robotcar` 已建立(空)。

```bash
# 0) 【PC】只上傳這個子資料夾(不含 .env、不含 data/)
rsync -av --exclude data/ --exclude .git/ --exclude .env --exclude __pycache__ --exclude '*.pyc' \
  ./stacks/robotcar/ jetson@192.168.183.219:/home/jetson/projects/robotcar/

# 1) 【Jetson】產生 .env 並依機器實況微調(見下方「上機前要對的幾個值」)
ssh j4012 'cd ~/projects/robotcar && cp -n .env.example .env && nano .env'

# 2) 【Jetson】建置四個自製映像(需 Wi-Fi:tts 會下載中文語音、各服務裝套件)
ssh j4012 'cd ~/projects/robotcar && docker compose build'

# 3) 【Jetson】先只起 ollama-new,拉 VLM 並做 GPU 實測(F1/N4 — 這是你核准的那步)
ssh j4012 'cd ~/projects/robotcar && docker compose up -d ollama-new'
ssh j4012 'docker exec robotcar-ollama-new-1 ollama pull llava'
#   在另一個視窗開 tegrastats,然後跑一次推論,看 GR3D_FREQ 是否「隨推論開始上升、結束後掉回」:
ssh j4012 'docker exec robotcar-ollama-new-1 sh -lc "ollama run llava \"describe a test image\" </dev/null" & sleep 1; timeout 20 tegrastats | grep -o "GR3D_FREQ [0-9]*%"'
#   ✅ GR3D 有隨推論上升→掉回 = 走 GPU,繼續。 ❌ 全程 0% = 退回 CPU,先停下重挑 image(見 DEPLOYMENT.md F1)。

# 4) 【Jetson】GPU 過了,再拉對話 LLM,起其餘服務
ssh j4012 'docker exec robotcar-ollama-new-1 ollama pull qwen2.5:3b'
ssh j4012 'cd ~/projects/robotcar && docker compose up -d'

# 5) 【Jetson】驗收
ssh j4012 'cd ~/projects/robotcar && bash ops/healthcheck/robotcar_healthcheck.sh'
ssh j4012 'cd ~/projects/robotcar && bash bin/see.sh'      # 相機→中文描述(喇叭沒開也會存 wav)
ssh j4012 'cd ~/projects/robotcar && bash bin/talk.sh'     # 對麥克風說話→中文回答
```

## 上機前要對的幾個值(`.env` / 首次除錯)
這些是「在裝置上才知道」的東西,首發時對一下:
- **PulseAudio UID/路徑**:`ssh j4012 id -u`(通常 1000)、`ls /run/user/<uid>/pulse`;對到 `.env` 的 `PULSE_SOCKET`。
- **藍芽喇叭**:打開藍芽喇叭並連上後,`ssh j4012 pactl list short sinks` 確認預設 sink 是它;`paplay` 預設就會走預設 sink。喇叭沒開也沒關係,TTS 一律會把 wav 存到 `data/logs/`。
- **麥克風來源**:`ssh j4012 pactl list short sources`;若預設不是 XVF3800,把來源名填進 asr 的 `PULSE_SOURCE`(compose environment 或 .env)。
- **相機**:預設用 index 0(對到 `/dev/video0`)。若有多顆,調 `.env` 的 `VIDEO_DEV`。
- **模型 tag**:`qwen2.5:3b` / `llava` 若某 tag 不存在,`docker exec robotcar-ollama-new-1 ollama list` 看實際可用的。

## 除錯(N3)
內部服務預設不對主機開 port。要直接打它們:
```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d   # 暫時開 asr:21501 / tts:21502 / vision:21503 / ollama:21434（都綁 127.0.0.1）
docker compose up -d                                                     # 收回,鎖回只剩 brain
```

## 回滾
```bash
bash ops/rollback/robotcar_rollback.sh            # 停並移除 5 個容器;模型/log 保留
bash ops/rollback/robotcar_rollback.sh --purge    # 連 data/(模型/log)一起刪(不可逆)
```
本 stack 完全獨立,回滾不會動到 JN1。JN1 服務的停用/還原是另一份 `../../ops/rollback/jn1_restore.sh`。

## 已知的「首發可能要在裝置上調」的點(誠實揭露)
- 容器內存取 `/dev/video0` 或 PulseAudio 若權限被擋,可能要補對應 group GID(裝置上 `getent group video audio` 查)。
- `faster-whisper` / `piper` / `dustynv-ollama` 的 arm64 行為以**裝置實測**為準(build 或首跑才算數)。
- 這些是邊緣裝置整合的正常收尾,已把每個服務拆成可獨立 `curl` 健檢,方便逐個定位。

## 🚀 一鍵部署(不用 Claude Code、不用逐步核准)
把整個 M1 一口氣跑到完。**在 PC 的 Git Bash**,於 `C:\000_J4012` 資料夾下貼這一行(可右鍵貼上,不用打字):
```
tar -C stacks/robotcar --exclude=data --exclude=.env --exclude=__pycache__ -czf - . | ssh j4012 'mkdir -p ~/projects/robotcar && tar -C ~/projects/robotcar -xzf - && cd ~/projects/robotcar && bash deploy_all.sh'
```
它會:上傳最新 stack → build → 起 ollama-new → 拉 llava+qwen → GPU 檢查 → 起全部服務 → healthcheck,全程紀錄在 Jetson 的 `~/projects/robotcar/data/logs/deploy_*.log`。**不碰 JN1**、可重複跑。

或直接**在 Jetson 上**(它有接螢幕鍵盤)開終端機跑:先確保檔案在,然後
```
cd ~/projects/robotcar && bash deploy_all.sh
```
跑完在 Jetson 上 `bash bin/see.sh`(看畫面)、`bash bin/talk.sh`(對它說話)驗收。

## ✅ 日常使用(M1 完成 2026-08-21)
機器車大腦平常就跑著(容器 `restart: unless-stopped`,開機自動起)。要用時在 Jetson 上:
```
bash bin/see.sh     # 看看前面:相機→中文描述→耳機唸出來
bash bin/talk.sh    # 對麥克風說話→中文回答→耳機唸出來
```
- 健檢:`bash ops/healthcheck/robotcar_healthcheck.sh`
- 收掉:`bash ops/rollback/robotcar_rollback.sh`(不碰 JN1)
- 記憶體:`ops/setup_dropcaches.sh` 裝的計時器每 60s 自動清快取,保持 GPU 有記憶體(已裝好)。
- 還原 JN1:`sudo systemctl enable --now ollama jn1-agent-bridge && docker update --restart=always jn1-ai-core && docker start jn1-ai-core`
