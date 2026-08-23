FROM python:3.10-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg pulseaudio-utils libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docker/asr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/asr/server.py .
ENV MODELSCOPE_CACHE=/models/modelscope
EXPOSE 8000
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8000"]
