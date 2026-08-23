# ReSpeaker 4-Mic Array 整合建議（M2b）

**日期**：2026-08-23
**唯讀聲明**：本文件所有「JN1_AI 參考設定」段落，均透過 `cat /home/jetson/JN1_AI/docker-compose.yaml` 讀取取得。**JN1_AI 資料夾全程唯讀，未做任何新增、修改、移動或刪除**。以下配置是在 `0_JN1_Robotcar` 內重新撰寫的獨立檔案，並非搬移或複製原檔。

## 1. JN1_AI 原始參考設定（唯讀取得，僅摘錄音訊相關部分）

```yaml
network_mode: "host"                # ReSpeaker 依賴 host 網路模式
privileged: true
group_add: ["audio", "video", "dialout", "plugdev"]
environment:
  - PULSE_SERVER=unix:/run/user/1000/pulse/native
  - PULSE_COOKIE=/run/user/1000/pulse/cookie
  - PULSE_SOURCE=alsa_input.usb-Seeed_Studio_reSpeaker_XVF3800_4-Mic_Array_114993701254100107-00.analog-stereo
volumes:
  - /run/user/1000/pulse:/run/user/1000/pulse
  - /home/jetson/.config/pulse/cookie:/run/user/1000/pulse/cookie
  - /dev/bus/usb:/dev/bus/usb
```

重點：JN1_AI 把 ReSpeaker 麥克風陣列指定為 PulseAudio 的固定輸入來源（`PULSE_SOURCE`），並掛載 `/dev/bus/usb` 讓容器能直接存取 USB 裝置。

## 2. Robotcar 現況與差異

- Robotcar 的 `asr` 服務**已經支援** `PULSE_SOURCE` 環境變數（`src/asr/server.py:18`：`SOURCE = os.environ.get("PULSE_SOURCE", "default")`），目前預設為系統預設輸入源，尚未指定 ReSpeaker。
- Robotcar 採 **service 個別掛載** 模式（非 host network），已有 `docker-compose.override.yml` 處理 PulseAudio cookie 認證，架構比 JN1_AI 的單一巨型容器更模組化，因此**不需要複製 JN1_AI 的 `network_mode: host` / `privileged: true`**，只需比照掛載 PulseAudio socket + 指定 source 即可。

## 3. 建議整合方式（已在 0_JN1_Robotcar 內建立，尚未套用）

已建立範例檔 [`docker-compose.respeaker.example.yml`](../docker-compose.respeaker.example.yml)（獨立於主要 `docker-compose.yml`，因為目前沒有 ReSpeaker 硬體可實測，先不預設套用）：

```yaml
services:
  asr:
    environment:
      - PULSE_SOURCE=alsa_input.usb-Seeed_Studio_reSpeaker_XVF3800_4-Mic_Array_XXXXXXXX-00.analog-stereo
    group_add: ["audio", "plugdev"]
    devices:
      - /dev/bus/usb:/dev/bus/usb
```

### 啟用步驟（硬體到位後）
1. 接上 ReSpeaker 後,在 host 執行 `pactl list sources short`,找到實際的 source 名稱(序號尾綴依裝置而異,需取代 `XXXXXXXX`)。
2. 疊加套用範例檔：
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.override.yml \
     -f docker-compose.respeaker.example.yml up -d --no-deps asr
   ```
3. 用 `curl -X POST http://127.0.0.1:8003/listen?seconds=5` 測試錄音是否切換到 ReSpeaker 收音。

## 4. 差異化建議（超越 JN1_AI 原始做法）

- **不建議**沿用 JN1_AI 的 `privileged: true` + host network 整包搬過來 — Robotcar 服務隔離架構（每服務獨立 container、`--no-deps` 部署）風險更低，只掛載必要的 PulseAudio socket 與 USB 裝置即可達到相同效果。
- ReSpeaker XVF3800 內建硬體波束成形(beamforming)與降噪，比目前預設輸入源更適合遠場語音辨識，待硬體採購到位後可直接套用本文件的範例檔，無需修改 `src/asr/server.py`（已原生支援 `PULSE_SOURCE`）。

## 5. 唯讀確認聲明

本次撰寫本文件過程中，僅對 `/home/jetson/JN1_AI/docker-compose.yaml` 執行 `cat` 讀取一次，**未對 JN1_AI 資料夾做任何寫入、修改、移動或刪除**。所有新產出（本文件、`docker-compose.respeaker.example.yml`）均位於 `/home/jetson/0_JN1_Robotcar/` 內。
