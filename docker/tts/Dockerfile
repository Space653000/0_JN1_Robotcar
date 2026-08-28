FROM dustynv/l4t-pytorch:r36.2.0

WORKDIR /app

# 安裝基礎工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 複製原有 Piper requirements（fallback）
COPY docker/tts/requirements.txt .

# 安裝 Piper 依賴（不要升級 torch/torchaudio，用 base 內建）
RUN pip install --no-cache-dir -r requirements.txt

# 克隆 CosyVoice（含 submodules）
RUN git clone --depth 1 --recurse-submodules https://github.com/FunAudioLLM/CosyVoice /app/cosyvoice 2>&1 || \
    git clone --depth 1 https://github.com/FunAudioLLM/CosyVoice /app/cosyvoice 2>&1

# 安裝 CosyVoice 依賴（不重裝 torch）
WORKDIR /app/cosyvoice
RUN pip install --no-cache-dir \
    matcha-tts \
    modelscope \
    funasr \
    WeTextProcessing \
    pydub \
    soundfile \
    julius || echo "部分依賴安裝警告"

WORKDIR /app

# 複製 TTS 服務代碼
COPY src/tts/server.py .

EXPOSE 8000
CMD ["python", "server.py"]
