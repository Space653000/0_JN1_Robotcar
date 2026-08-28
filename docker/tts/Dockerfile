FROM python:3.10-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      pulseaudio-utils curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docker/tts/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /models && \
    curl -fsSL -o /models/kokoro-v1.0.onnx \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx && \
    curl -fsSL -o /models/voices-v1.0.bin \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
RUN mkdir -p /voices && \
    curl -fsSL -o /voices/zh_CN-huayan-medium.onnx \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx && \
    curl -fsSL -o /voices/zh_CN-huayan-medium.onnx.json \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json
COPY src/tts/server.py .
EXPOSE 8000
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8000"]
