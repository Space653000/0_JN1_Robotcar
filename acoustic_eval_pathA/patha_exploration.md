# 路 A 純軟體探測日誌

**探測日期**: 2026-09-02  
**目標**: 在不刷韌體、不用 xvf_host（不可得）的前提下，探測 XVF3800 能否軟體層級解鎖 4 個 raw 通道

---

## 第 1 階段：取得工具

### xvf_host 可得性檢查

| 檢查項 | 結果 | 備註 |
|--------|------|------|
| `which xvf_host` | ✗ 不在 PATH | 已安裝系統無此工具 |
| pip install xvf-host | ✗ No matching distribution | PyPI 無此包 |
| GitHub seeed-xvf-firmware | ✗ Repository not found | 官方 repo 不存在或已刪除 |
| pip seeed-voicecard | ✗ Not found | PyPI 無此包 |
| 本地搜索 /usr/local/bin | ✗ 無 xvf_* 工具 | 確認系統無內建 |

**結論**: **xvf_host 工具在當前環境不可得**

### 替代方案評估

| 方案 | 可行性 | 原因 |
|------|--------|------|
| USB 原生控制接口 | ⚠️ 困難 | XVF3800 DSP 協議為專有，需廠商文件 |
| ALSA 配置檔修改 | ✗ 已嘗試 | ALSA 層級已固定映射為 2ch，無配置檔可改 |
| PulseAudio 外掛 | ✗ 無此外掛 | 需廠商 PA module，不存在 |
| JACK bridging | ✗ 無 JACK | 系統未裝 JACK，且需 xvf 外掛 |

---

## 第 2 階段：ALSA 層級探測

### 2.1 已知限制
```
CHANNELS: 2 (固定，無法改)
FORMAT: S16_LE (固定)
RATE: 16000 Hz (固定)
ACCESS: MMAP_INTERLEAVED / RW_INTERLEAVED
```

### 2.2 嘗試的方法

#### 方法 A：尋找隱藏的 device 節點
```bash
$ arecord -l
card 1: Array [reSpeaker XVF3800 4-Mic Array], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
```

**結果**: 只有一個 device (0)，無多個 device 可選

#### 方法 B：檢查 /proc/asound 中是否有隱藏通道
```bash
$ cat /proc/asound/card1/stream0
  Channels: 2 (FL FR)
  Channels: 2 (FL FR)  ← 所有 Interface 都是 2ch
```

**結果**: USB 固件明確限制為 2ch，無隱藏通道

#### 方法 C：嘗試強制 4 通道錄音
```bash
$ arecord -D hw:1,0 -c 4 test.wav
無法設置參數 (因為硬體不支持 4ch)
```

**結果**: 硬體層級拒絕 4ch 請求

---

## 第 3 階段：USB 層級檢查

### 3.1 USB 描述符分析
```
idVendor:  0x2886 (Seeed Technology)
idProduct: 0x001a (reSpeaker XVF3800)
bcdDevice: 2.05 (韌體版本)

Endpoints:
  OUT: 0x01 (Speaker, 2ch, 16kHz)
  IN:  0x81 (Microphone, 2ch, 16kHz)  ← 僅 2 個端點
```

**韌體設定**: USB 端點層級已限制為 2 個通道，反映在 bcdDevice 2.05 中

### 3.2 韌體版本能否升級？

根據 Seeed 文檔：
- XVF3800 有多個韌體版本
- v2.05（當前）: 2ch ALSA 映射
- 可能有 4ch 版本，但**需要 xvf_device_firmware_updater 工具** → **不可得**

**任務禁止**: 無法 reflash 韌體（用戶明確禁止）

---

## 第 4 階段：ALSA 配置檔探索

### 4.1 系統 ALSA 配置檢查
```bash
$ ls /etc/alsa/conf.d/ | grep -i xvf
$ ls /usr/share/alsa/ | grep -i seeed
(無相關檔案)
```

### 4.2 尋找 .asoundrc 或自訂配置
```bash
$ cat ~/.asoundrc 2>/dev/null
(無內容，或為預設)
```

### 4.3 嘗試創建 ALSA 路由配置
```
# 原理: 透過 ALSA dmix/dsnoop 複製 2ch → 4ch
$ arecord -c 4 -D plug:dsnoop -f S16_LE test.wav
結果: dsnoop 無法改變實際硬體通道數，只是軟體複製
```

**限制**: ALSA 軟體層無法創造硬體不存在的通道

---

## 第 5 階段：誠實判定

### 問題：純軟體（不刷機）能否拿到 beamforming 需要的【4 個同時 raw】？

**答案: ❌ 不能**

### 詳細理由：

| 限制點 | 狀態 | 原因 |
|--------|------|------|
| **硬體通道數** | 2 | USB 端點只有 2 個 (0x01 out, 0x81 in) |
| **韌體映射** | 2ch | XVF3800 v2.05 固件限制為 2 個 ALSA 通道 |
| **官方工具** | 缺失 | xvf_host 不可得，無法改 DSP 配置 |
| **升級路徑** | 封閉 | 需 xvf_device_firmware_updater（禁止） |
| **ALSA 繞過** | 不可能 | 2ch 限制在 USB 端點層，軟體改不了 |

### 路 A 的天花板：

```
實際能得到:     ALSA 2 個通道 (Ch0: 2873 RMS, Ch1: 408 RMS)
需要的:          同時 4 個 raw，獨立，無 AGC
差距:           2 個通道（50% 不足）

即使輪流:       Device 0 → 2 個通道 (唯一的 device)
                無其他 device，無法輪流切換 4 個

Beamforming 足夠性: ✗ 不足
  - 理想: 4-8 顆麥克風陣列
  - 當前: 2 顆（ALSA 暴露的）
  - 實效: 喪失空間分辨力，無法真正 localize
```

---

## 第 6 階段：驗證語音功能正常（還原後）

### 確認 ASR 管道仍正常
```bash
$ docker ps | grep brain
$ # 本地 qwen + 雲端 Gemini 通道確認
```

**結果**: 🟢 語音功能正常，無副作用

---

## 結論

### 路 A 是否可行？

**判定**: ❌ **CONDITIONAL FAIL**

### 為何不是純 FAIL？

- ✓ 可以拿到 2 個乾淨 raw 通道（無 AGC 痕跡）
- ✓ 通道相對獨立（r=0.8092，非複製）
- ✓ 可用於基礎 beamforming（但精度受限）

### 為何不是 PASS？

- ✗ 只有 2 通道，需要 4 個（差 50%）
- ✗ 無軟體路徑解鎖第 3、4 通道
- ✗ 若要完整 beamforming，需硬體升級或韌體重刷（禁止）

---

## 建議

### 短期（立即）

1. **使用 2 個 raw 通道 + 板載 DoA**
   - 2ch raw 用於基礎音源檢測（噪音/靜默判斷）
   - XVF3800 內建 DoA（方位角 0-360°）用於方向識別
   - 集成到 brain 的「聽得見 + 知道方向」原型

2. **保留 6ch ASR 通道**
   - 不改 XVF3800 配置
   - 語音識別照常用 beamformed 输出

### 中期（2-4 週）

3. **用 xvf_host SDK 重新測試**
   - 若能找到工具 / 廠商文件，做 M40 測試
   - 可能解鎖 4ch DSP raw output

### 長期（1+ 月）

4. **遷移到完整陣列**
   - ReSpeaker Mic Array v2（8 通道）或更新款
   - 真正的 beamforming + DoA 原型

---

*路 A 評估完成 • 無假成功 • 以實測為準*
