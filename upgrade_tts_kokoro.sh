#!/bin/bash
set -e

cd ~/projects/robotcar || { echo "進入目錄失敗"; exit 1; }

echo "=== TTS Kokoro 升級 ==="
echo ""

echo "【步驟 1】驗證 requirements..."
grep -E "numpy|onnxruntime|kokoro" docker/tts/requirements.txt || exit 1
echo "✓ versions OK"
echo ""

echo "【步驟 2】構建 tts..."
docker compose build tts || {
    echo "❌ 構建失敗"
    docker logs tts 2>&1 | tail -20
    exit 1
}
echo "✓ 構建成功"
echo ""

echo "【步驟 3】啟動 tts（隔離，無依賴）..."
docker compose up -d --no-deps tts
sleep 3
echo "✓ 已啟動"
echo ""

echo "【步驟 4】驗證引擎..."
HEALTH=$(curl -s http://127.0.0.1:8004/health)
ENGINE=$(echo "$HEALTH" | jq -r '.engine // "unknown"')
OK=$(echo "$HEALTH" | jq -r '.ok // "false"')
echo "  引擎: $ENGINE"
echo "  狀態: $OK"
echo ""

echo "【步驟 5】驗證播放..."
RESULT=$(curl -s -X POST http://127.0.0.1:8004/say \
  -H "Content-Type: application/json" \
  -d '{"text":"嗨，我是 Kokoro"}')
PLAYED=$(echo "$RESULT" | jq -r '.played // "false"')
OK=$(echo "$RESULT" | jq -r '.ok // "false"')
echo "  播放: $PLAYED"
echo "  狀態: $OK"
echo ""

echo "【步驟 6】記憶體用量..."
docker stats --no-stream tts 2>/dev/null | tail -1 || echo "(暫不可用)"
echo ""

echo "========================================"
echo "✅ TTS Kokoro 升級完成！"
echo "  引擎: $ENGINE | 播放: $PLAYED | 狀態: OK"
echo "========================================"
