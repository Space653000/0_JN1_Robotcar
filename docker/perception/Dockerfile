FROM dustynv/l4t-pytorch:r36.2.0

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies for camera access + OpenCV (PyTorch already has CUDA)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsm6 libxext6 libxrender-dev \
    libv4l-0 libv4l-dev \
    libgl1 libglvnd0 libglx0 \
    libglib2.0-0 libgthread-2.0 \
    && rm -rf /var/lib/apt/lists/*

# Install ultralytics + fastapi + uvicorn (torch/pytorch already in base)
RUN pip install --no-cache-dir \
    ultralytics==8.0.227 \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    opencv-python==4.8.1.78

# Copy application
COPY src/perception/ /app/

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
