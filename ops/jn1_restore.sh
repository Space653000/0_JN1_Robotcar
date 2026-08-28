#!/bin/bash
set -e
cd /home/jetson/0_JN1_Robotcar
echo "【JN1 還原】$(date '+%F %T')"
echo "[1] 取 tag"
git fetch --tags 2>&1 | tail -1
echo "[2] 檢出穩定點(docker/src/compose)"
git checkout stable-senseVoice -- docker src docker-compose.yml
echo "[3] 重建容器"
docker compose up -d --build 2>&1 | tail -4
sleep 10
echo "[4] 檢查/補模型(持久化於 data/ollama-new)"
for m in $(grep -v '^#' data/MODELS_REQUIRED.txt); do
  if docker exec robotcar-ollama-new-1 ollama show "$m" >/dev/null 2>&1; then 
    echo "  ✓ $m 已在"
  else 
    echo "  ✗ $m 缺，re-pull..."
    docker exec robotcar-ollama-new-1 ollama pull "$m" 2>&1 | tail -2
  fi
done
echo "[5] 健康檢查"
curl -s http://localhost:21500/health 2>&1 | head -3
echo ""
echo "【還原完成】$(date '+%F %T')"
