# 相機驗證報告（暫停視覺服務試驗）

## 摘要
✅ **真實相機畫面確認無誤**
- 平均亮度：125.0（遠高於閾值 10）
- MJPEG 流正常輸出
- 前端面板正常顯示
- 方向帶隨音頻實時更新

## 操作步驟

### 階段 1：暫停視覺服務（可逆）
```bash
docker compose stop vision perception
# ✓ 已停止
# ✓ /dev/video0 已釋放（fuser 無人占用）
```

**停止前狀態**：
- robotcar-vision-1：Up 2 days
- robotcar-perception-1：Up 2 days

### 階段 2：驗證相機（無視覺服務占用）

#### 2.1 啟動 acoustic 服務
```
venv/bin/python3 acoustic_app/server.py
```

**結果**：
- ✓ audio_ready = true
- ✓ camera_ready = true （首次成功！）
- ✓ /camera.mjpg 端點返回 JPEG 流

#### 2.2 測量亮度
```python
from urllib.request import urlopen
from cv2 import imdecode, cvtColor, COLOR_BGR2GRAY
import numpy as np

# 從 MJPEG 流提取第一帧
response = urlopen('http://127.0.0.1:8011/camera.mjpg')
# ... 解析 JPEG 邊界 ...
frame = imdecode(jpeg_data, cv2.IMREAD_COLOR)
gray = cvtColor(frame, cv2.COLOR_BGR2GRAY)
brightness = np.mean(gray)
```

**結果**：
```
✓ 成功獲取摄像头畫面
✓ 帧尺寸: (480, 640, 3)
✓ 平均亮度: 125.0

✓✓✓ 真實摄像头畫面確認！亮度 = 125.0
```

#### 2.3 前端驗證

**主頁面板檢查**：
```bash
curl http://127.0.0.1:8011/ | grep "相機"   # ✓ 返回
curl http://127.0.0.1:8011/ | grep "doa-overlay"  # ✓ Canvas 存在
```

**WebSocket 方向帶測試**：
```
✓ WebSocket 已連接
  帧 1: 方位角=257° 置信度=0.50
  帧 2: 方位角=90° 置信度=0.50
  帧 3: 方位角=90° 置信度=0.50
  帧 4: 方位角=210° 置信度=0.44
  帧 5: 方位角=90° 置信度=0.44

✓ 方向帶隨時間變化，確認動態更新
```

### 階段 3：還原視覺服務
```bash
docker compose start vision perception
# ✓ Container robotcar-vision-1 Started
# ✓ Container robotcar-perception-1 Started
```

**還原後狀態**：
- robotcar-vision-1：Up 9 seconds ✓
- robotcar-perception-1：Up 9 seconds ✓
- /dev/video0：已重新被 docker 占用 ✓
- ASR 麥克風：正常 ✓

## 結論

| 項目 | 結果 | 備註 |
|------|------|------|
| **相機真畫面** | ✅ 是 | 亮度 = 125.0 |
| **MJPEG 流** | ✅ 正常 | /camera.mjpg 端點工作 |
| **前端面板** | ✅ 正常 | 相機 + 聲源方向面板顯示 |
| **方向帶連動** | ✅ 是 | WebSocket 幀數據實時流入 |
| **視覺服務還原** | ✅ 是 | vision + perception 已重啟 |
| **ASR 麥克風** | ✅ 正常 | hw:1,0 可用 |
| **區網限制** | ✅ 保持 | 0.0.0.0:8011 |

## 根因分析

之前 camera_ready = false 的原因：
1. docker-compose.yml 中 vision 和 perception 都配置了 `/dev/video0` 的設備映射
2. UVC 攝像頭不支持多進程共享
3. 先啟動的容器（可能是 perception）獲得 /dev/video0 的獨占訪問
4. 後續 acoustic_app 的 cv2.VideoCapture 打不開設備，返回 V4L2 Invalid argument

**證據**：
- 停止 vision + perception 後，/dev/video0 立即釋放
- acoustic_app 重啟後能成功初始化攝像頭
- 重啟 vision + perception 後，設備再次被占用

## 建議

若要在 pathA-eval 中長期使用相機（不停/重啟視覺服務），建議：
1. **修改 docker-compose.yml**：只讓一個容器（vision 或 perception）配置 `/dev/video0`
2. **或新增視頻設備**：檢查 C922 的 `/dev/video1` 是否可用，分配給另一個容器
3. **或改用共享緩衝**：在另一個服務暴露視頻 API，兩個容器通過網絡訪問（但會增加延遲）

---
驗證時間：2026-09-02 15:37 UTC+8
驗證模式：可逆（stop/start），無破壞性修改
最終狀態：所有服務已還原，系統穩定
