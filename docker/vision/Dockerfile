FROM dustynv/l4t-pytorch:r36.2.0

WORKDIR /app

# 安裝基礎工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libopenjp2-7 \
    libtiff6 \
    && rm -rf /var/lib/apt/lists/*

# 安裝 moondream2 + transformers 依賴
RUN pip install --no-cache-dir \
    transformers \
    accelerate \
    pillow \
    einops \
    torchvision \
    opencv-python \
    2>&1 || echo "部分依賴安裝警告"

# 複製 Vision 服務代碼
COPY src/vision/server.py .

EXPOSE 8000
CMD ["python", "server.py"]
