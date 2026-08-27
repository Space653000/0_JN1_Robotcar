FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies for camera access + OpenCV + GL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsm6 libxext6 libxrender-dev \
    libv4l-0 libv4l-dev \
    libgl1 libglvnd0 libglx0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY docker/perception/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application
COPY src/perception/ /app/

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
