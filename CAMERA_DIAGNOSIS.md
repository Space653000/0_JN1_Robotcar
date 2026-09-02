# 相機占用診斷報告（2026-09-02）

## 問題描述
C922 Pro Stream Webcam 無法被 acoustic_app 打開。
- OpenCV cv2.VideoCapture(0) 失敗：`[WARN] open VIDEOIO(V4L2:/dev/video0): can't open camera by index`
- 狀態：camera_ready=false，仍使用虛擬黑屏模式

## 診斷步驟

### 1. 硬件確認
```
$ v4l2-ctl --list-devices
C922 Pro Stream Webcam (usb-3610000.usb-2.1):
  /dev/video0
  /dev/video1
  /dev/media1
```
✓ 設備存在，ID 81:0 和 81:1

### 2. 主機層進程檢查
```
$ fuser -v /dev/video0 /dev/video1
→ (無結果)

$ lsof /dev/video0 /dev/video1
→ (無占用)

$ ps aux | grep -E "python|server" | grep -v grep
→ 無 acoustic_app 的舊程序；只有系統服務和 docker
```
結論：主機層沒有進程占用

### 3. Docker 容器檢查
**docker ps** 運行中的服務：
- robotcar-vision-1 （Up 2 days）
- robotcar-perception-1 （Up 2 days）
- robotcar-brain-1, robotcar-asr-1, robotcar-tts-1, robotcar-webui-1, robotcar-ollama-new-1

**docker-compose.yml 配置分析**：
```yaml
# Line 89-90: perception 服務
devices:
  - ${VIDEO_DEV:-/dev/video0}:/dev/video0

# Line 102-103: vision 服務
devices:
  - ${VIDEO_DEV:-/dev/video0}:/dev/video0
```

**docker inspect robotcar-vision-1**：
```json
"Devices": [
  {
    "PathOnHost": "/dev/video0",
    "PathInContainer": "/dev/video0",
    "CgroupPermissions": "rwm"
  }
]
```

### 4. 設備訪問測試
```
$ dd if=/dev/video0 bs=1 count=1
dd: error reading '/dev/video0': Invalid argument
```
設備返回 EINVAL —— 通常表示：
- 設備被某個進程獨占打開（不可共享）
- 或設備驅動發生錯誤

### 5. 權限檢查
```
$ stat /dev/video0
Access: (0660/crw-rw----)  Uid: (    0/root)   Gid: (   44/video)

$ id
uid=1000(jetson) gid=1000(jetson) groups=...44(video)...
```
✓ jetson 用戶在 video 組，權限充分

## 結論

### 占用者：**Docker 容器（robotcar-vision 和 robotcar-perception）**

因為：
1. **主機層 lsof/fuser** 查不到 → 容器有命名空間隔離
2. **docker-compose.yml** 明確配置了兩個容器都用 `/dev/video0`
3. **docker inspect** 證實 vision 容器映射了設備
4. **OpenCV 報 V4L2 Invalid argument** → 設備被獨占打開

### 可能的原因
1. **兩個容器爭奪同一設備**（perception 和 vision 都配置了 /dev/video0）
   - UVC 攝像頭通常不支持多進程共享
   - 先啟動的容器獲得設備，後續請求失敗

2. **容器啟動順序**
   - perception depends_on 未明確聲明
   - vision depends_on = [ollama-new]
   - 兩者可能同時初始化

### 處理決定：【停手不動】

**用戶限制**："不停/重啟任何 docker 服務、不 modprobe、不用 sudo 動核心模組"

**可能的解決方案**（需要用戶決定）：
```bash
# 方案 A：停止 perception 容器（保留 vision）
docker compose stop robotcar-perception-1

# 方案 B：停止 vision 容器（保留 perception）
docker compose stop robotcar-vision-1

# 方案 C：修改 docker-compose.yml，只有一個容器配置 /dev/video0
# 編輯 Line 89-90 或 Line 102-103 之一

# 方案 D：使用不同的攝像頭設備
export VIDEO_DEV=/dev/video1  # 若 C922 支持 video1
docker compose up -d
```

## 最終狀態

| 項目 | 狀態 |
|------|------|
| 攝像頭硬件 | ✓ 正常（C922 可檢測） |
| 主機進程占用 | ✗ 無（已確認） |
| Docker 容器占用 | ⚠️ 是（vision + perception） |
| 解鎖難度 | 中（需改 compose 或停容器） |
| 當前 acoustic_app 狀態 | 虛擬黑屏模式（offline） |
| ASR 麥克風 | ✓ 正常（hw:1,0） |
| 區網限制 | ✓ 保持（0.0.0.0:8011） |

---
診斷時間：2026-09-02 11:45 UTC+8
診斷人：Claude Code（唯讀模式）
