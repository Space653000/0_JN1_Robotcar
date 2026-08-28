# JN1 全系統盤點

日期：2026-08-28 23:30 UTC

---

## 1. 硬體 (HW)

### 型號
```
### 型號
```

```

### 記憶體 / 儲存空間
```
               total        used        free      shared  buff/cache   available
Mem:            15Gi       8.9Gi       3.3Gi       126Mi       3.1Gi       6.0Gi
Swap:           23Gi       895Mi        22Gi

Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p1  915G  482G  397G  55% /
/dev/nvme0n1p1  915G  482G  397G  55% /
```

### 即時資源 (tegrastats)
```
```

### 電源模式
```
```

---

## 2. 韌體 / OS

### Tegra 版本
```
```

### JetPack 版本
```
```

### Kernel
```
Linux jetson-superJ4012 5.15.148-tegra #1 SMP PREEMPT Thu Sep 18 15:08:33 PDT 2025 aarch64 aarch64 aarch64 GNU/Linux
```

### OS 信息
```
```

### CUDA 版本
```
```

---

## 3. Docker / 服務

### Docker 版本
```
Docker version 29.7.2, build a7dcaa6
Docker Compose version v5.5.0
```

### 運行容器
```
NAME                    IMAGE                                    COMMAND                  SERVICE      CREATED             STATUS             PORTS
robotcar-asr-1          robotcar-asr:0.2.0                       "uvicorn server:app …"   asr          About an hour ago   Up About an hour   127.0.0.1:8003->8000/tcp
robotcar-brain-1        robotcar-brain:0.2.0                     "uvicorn server:app …"   brain        About an hour ago   Up About an hour   127.0.0.1:21500->8000/tcp
robotcar-ocr-1          robotcar-ocr:0.1.0                       "uvicorn server:app …"   ocr          34 hours ago        Up 34 hours        127.0.0.1:8002->8000/tcp
robotcar-ollama-new-1   dustynv/ollama:0.6.8-r36.4-cu126-22.04   "/bin/bash -c '/star…"   ollama-new   About an hour ago   Up About an hour   11434/tcp
robotcar-perception-1   robotcar-perception:1.0.0                "uvicorn server:app …"   perception   About an hour ago   Up About an hour   127.0.0.1:8001->8000/tcp
robotcar-tts-1          robotcar-tts:latest                      "uvicorn server:app …"   tts          About an hour ago   Up About an hour   127.0.0.1:8004->8000/tcp
robotcar-vision-1       robotcar-vision:latest                   "uvicorn server:app …"   vision       About an hour ago   Up About an hour   8000/tcp
robotcar-webui-1        robotcar-webui:1.0.0                     "uvicorn server:app …"   webui        About an hour ago   Up About an hour   0.0.0.0:8080->8000/tcp
```

### 鏡像清單
```
dustynv/l4t-ml:r36.4.0                     30335fe526e4       24.4GB             0B        
dustynv/l4t-pytorch:r36.2.0                0927a65739c2       13.8GB             0B        
dustynv/ollama:0.6.8-r36.4-cu126-22.04     7b3461ad91ad       9.96GB             0B   U    
dustynv/ollama:r36.4-cu129-24.04           05a4456e569c       8.78GB             0B        
robotcar-asr:0.1.0                         ab118dae1fea        950MB             0B        
robotcar-asr:0.2.0                         9f9e3de11091       1.65GB             0B   U    
robotcar-brain:0.1.0                       6ef27008dade        191MB             0B        
robotcar-brain:0.2.0                       d9f48408d7f3        192MB             0B   U    
robotcar-ocr:0.1.0                         adc2c269133d       1.34GB             0B   U    
robotcar-perception:1.0.0                  a1bb933ebb3c       14.3GB             0B   U    
robotcar-tts:0.1.0                         3dacc1afd437        868MB             0B        
robotcar-tts:0.2.0                         ce4622249541        707MB             0B        
robotcar-tts:latest                        1ff0ece909d9        605MB             0B   U    
robotcar-vision:0.1.0                      976b4d0f956f       13.9GB             0B        
robotcar-vision:latest                     b4f41dc706e5        527MB             0B   U    
robotcar-webui:1.0.0                       557d6a101395        196MB             0B   U    
```

---

## 4. LLM / 模型

### Ollama 模型
```
```

### 服務引擎配置
```
      - ASR_ENGINE=${ASR_ENGINE:-sensevoice}      # sensevoice | whisper(fallback)
      - ASR_LANG=${ASR_LANG:-zh}
      - TTS_ENGINE=piper
      - VLM_MODEL=${VLM_MODEL:-llava}
```

### 模型檔案
```
224K	data/hf/modules
3.6G	data/hf/moondream2
./data/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx
./data/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.onnx
./data/hf/moondream2/model.safetensors
./data/tts-models/models--FunAudioLLM--CosyVoice2-0.5B/snapshots/eec1ae6c79877dbd9379285cf8789c9e0879293d/flow.decoder.estimator.fp32.onnx
./data/tts-models/models--FunAudioLLM--CosyVoice2-0.5B/snapshots/eec1ae6c79877dbd9379285cf8789c9e0879293d/speech_tokenizer_v2.onnx
./data/tts-models/models--FunAudioLLM--CosyVoice2-0.5B/snapshots/eec1ae6c79877dbd9379285cf8789c9e0879293d/speech_tokenizer_v2.batch.onnx
./data/tts-models/models--FunAudioLLM--CosyVoice2-0.5B/snapshots/eec1ae6c79877dbd9379285cf8789c9e0879293d/campplus.onnx
./data/tts-models/models--FunAudioLLM--CosyVoice2-0.5B/snapshots/eec1ae6c79877dbd9379285cf8789c9e0879293d/CosyVoice-BlankEN/model.safetensors
```

---

## 5. 檔案 / Git

### Git 狀態
```
jn1-work
955b6bd M18b: Python 複查 vision — 確認容器掛機
a17c5bf M18: 確認 vision 容器內網真實狀態
479eb24 M16: 回到乾淨生產狀態，moondream2 測試殘留已清理
2cb41a8 M15f: moondream2 最強突破 — 9 次詳細嘗試後確認無法加載（HF 動態模塊 + 網路限制）
4452bce M15e: moondream2 隔離 docker run 測試
a2c3964 M15d: moondream2 真最後一發 — numpy 釘版失敗，永久擱置（8 次嘗試完結）
stable-senseVoice
```

### 檔案統計
```
總檔案數：157
目錄分布：
     73 data
     22 docker
     16 ops
     11 src
      4 docs
      3 poc
      2 "docs
      2 bin
      1 yolo11n.pt
      1 upgrade_tts_kokoro.sh
```

### 源代碼結構
```
src/vision/server.py
src/vision/server_lazy.py
src/tts/server.py
src/webui/server.py
src/asr/server.py
src/depth/server.py
src/perception/server.py
src/perception/labels_zh.json
src/brain/server.py
src/brain/tools.py
src/ocr/server.py
src/vision/__pycache__/server.cpython-310.pyc
src/tts/__pycache__/server.cpython-310.pyc
docker/vision/Dockerfile.m15
docker/vision/Dockerfile
docker/vision/Dockerfile.ollama-backup
docker/vision/requirements.txt
docker/vision/Dockerfile.lastshot
docker/vision/Dockerfile.lazy
docker/tts/Dockerfile.piper-backup
docker/tts/Dockerfile.simple
docker/tts/Dockerfile
docker/tts/requirements.txt
docker/webui/Dockerfile
docker/webui/requirements.txt
docker/asr/Dockerfile
docker/asr/requirements.txt
docker/depth/Dockerfile
docker/depth/requirements.txt
docker/perception/Dockerfile
docker/perception/requirements.txt
docker/brain/Dockerfile
docker/brain/requirements.txt
docker/ocr/Dockerfile
docker/ocr/requirements.txt
```

### Git 工作樹狀態
```
?? data/vision_snapshots/M19_full_inventory.md
```

---

## 6. 運行健康檢查

### 各服務健康狀態
```
8003: {"ok":true,"engine":"sensevoice","lang":"zh","hotwords":["JN1","Kokoro","Jetson"]}
8004: {"ok":true,"engine":"piper","voice":"zh_CN-huayan-medium"}
8001: {"ok":true,"model":"yolo11n","camera":"/dev/video0","confidence_threshold":0.5,"latest_inference_ms"
21500: {"ok":true,"services":{"ollama":true,"asr":true,"tts":true,"perception":true,"vision":true,"ocr":tru
```

### 備註
- Vision (8000)：無主機埠映射，由 brain 綜合 health 的 services.vision 反映
