FROM dustynv/l4t-pytorch:r36.2.0

WORKDIR /app

# 安裝基礎工具（git 足夠）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/* || true

# 安裝 moondream2 + transformers 依賴（使用鏡像源）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
    transformers accelerate pillow einops \
    2>&1 || pip install transformers accelerate pillow einops

# 複製 Vision 服務代碼
COPY src/vision/server.py .

EXPOSE 8000
CMD ["python", "server.py"]
