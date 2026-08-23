FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docker/brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/brain/ /app/
EXPOSE 8000
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8000"]
