#!/usr/bin/env bash
# Stop & remove the robotcar stack. Models/logs under ./data are KEPT unless --purge.
# Never touches JN1 services or JN1 data. (JN1 restore is a separate script.)
set -u
cd "$(dirname "$0")/../.." || exit 1
docker compose down
if [ "${1:-}" = "--purge" ]; then
  echo "Removing ./data/ollama-new and ./data/logs (irreversible model/log delete)."
  rm -rf ./data/ollama-new ./data/logs
fi
echo "robotcar stopped. JN1 services untouched by this script."
