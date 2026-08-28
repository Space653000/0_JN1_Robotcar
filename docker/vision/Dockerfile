FROM dustynv/l4t-pytorch:r36.2.0

WORKDIR /app

# 安裝基礎工具（git 足夠）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/* || true

# 安裝 moondream2 + transformers 依賴（不重裝 torch/torchvision）
RUN pip install --no-cache-dir \
    transformers \
    accelerate \
    pillow \
    einops \
    2>&1 || echo "部分依賴安裝警告"

# 複製 Vision 服務代碼
COPY src/vision/server.py .

EXPOSE 8000
CMD ["python", "server.py"]
