#!/usr/bin/env bash
# "看看前面": grab a camera frame, describe it, speak. Run on the Jetson.
set -u
PORT="${BRAIN_PORT:-21500}"
echo "[看一下畫面...]"
curl -s -X POST "http://127.0.0.1:${PORT}/see" | python3 -m json.tool --no-ensure-ascii 2>/dev/null || echo
