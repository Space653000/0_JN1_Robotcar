#!/usr/bin/env bash
# One-shot deploy for M2 voice+vision upgrade (brain v2 + ASR v2 + TTS v2).
# Runs on the Jetson. Does NOT start ocr/depth (on-demand). No movement.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "[1/4] building changed images (asr tts brain, vision unchanged)…"
docker compose build asr tts brain
echo "[2/4] (re)starting core stack…"
docker compose up -d ollama-new asr tts vision brain
echo "[3/4] ensuring base models present in ollama-new…"
for m in "${LLM_MODEL:-qwen2.5:3b}" "${VLM_MODEL:-llava}"; do
  docker compose exec -T ollama-new ollama list | grep -q "${m%%:*}" || \
    docker compose exec -T ollama-new ollama pull "$m" || true
done
echo "[4/4] waiting for brain health…"
for i in $(seq 1 30); do
  sleep 3
  curl -sf "http://127.0.0.1:${BRAIN_PORT:-21500}/health" >/dev/null && break
done
curl -s "http://127.0.0.1:${BRAIN_PORT:-21500}/health" | python3 -m json.tool || true
echo "done. run ops/verify_m2_voice.sh to check the gates."
