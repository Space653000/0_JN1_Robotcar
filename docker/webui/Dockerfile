FROM python:3.10-slim-bookworm

WORKDIR /app

# 安裝依賴
COPY docker/webui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用
COPY src/webui/server.py .

# 暴露端口
EXPOSE 8000

# 執行
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
