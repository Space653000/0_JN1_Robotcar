# Depth Anything V2 needs torch w/ CUDA -> Jetson-native torch base.
# Terminal: confirm the exact dustynv pytorch tag for L4T r36.4/cu126.
FROM dustynv/pytorch:2.3-r36.4.0
WORKDIR /app
COPY docker/depth/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/depth/server.py .
ENV HF_HOME=/models/hf
EXPOSE 8000
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8000"]
