FROM dustynv/l4t-pytorch:r36.2.0

WORKDIR /app

# 安裝基礎工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*

# 安裝 Piper TTS 依賴
COPY docker/tts/requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
    -r requirements.txt 2>&1 || pip install -r requirements.txt

# 可選：嘗試安裝 CosyVoice2（失敗不中止）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
    cosyvoice 2>&1 || echo "CosyVoice 安裝失敗，使用 Piper fallback"

# 複製 TTS 服務代碼
COPY src/tts/server.py .

EXPOSE 8000
CMD ["python3", "server.py"]
