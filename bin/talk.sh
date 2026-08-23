#!/usr/bin/env bash
# Push-to-talk: record from the mic, think, speak back. Run on the Jetson.
set -u
PORT="${BRAIN_PORT:-21500}"
SEC="${1:-}"
echo "[聽你說話 ${SEC:-預設}s...] 說話後稍等"
if [ -n "$SEC" ]; then
  curl -s -X POST "http://127.0.0.1:${PORT}/talk?seconds=${SEC}"
else
  curl -s -X POST "http://127.0.0.1:${PORT}/talk"
fi | python3 -m json.tool --no-ensure-ascii 2>/dev/null || echo
