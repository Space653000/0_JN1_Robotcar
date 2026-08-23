#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/../.." || exit 1
PORT="${BRAIN_PORT:-21500}"
echo "== robotcar containers =="
docker compose ps
echo "== brain /health =="
curl -s "http://127.0.0.1:${PORT}/health" | python3 -m json.tool --no-ensure-ascii 2>/dev/null || echo "brain not reachable"
echo "== resources =="
free -h | head -2
