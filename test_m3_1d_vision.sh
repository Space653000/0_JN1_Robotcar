#!/bin/bash
# M3-1d 中文視覺三場景測試腳本
# 每個場景：打印提示 → sleep 10 秒 → 拍攝 → 記錄回覆

set -e

BRAIN_URL="http://127.0.0.1:21500"
LOGFILE="/home/jetson/0_JN1_Robotcar/test_m3_1d_results.log"

# 初始化日誌
cat > "$LOGFILE" << 'EOF'
=== M3-1d 中文視覺三場景測試 ===
測試時間：$(date '+%Y-%m-%d %H:%M:%S')
管線：moondream(英文) → qwen2.5:3b(翻譯) → opencc(繁體)

EOF

echo "=== M3-1d 視覺翻譯樞紐測試開始 ==="

# 場景 1：水瓶
echo ""
echo "▶ 場景 1/3 ▶▶▶ 請在鏡頭前放【一個水瓶】，10秒後自動拍攝..."
for i in {10..1}; do
  echo -n "$i "
  sleep 1
done
echo ""
echo "📷 拍攝中..."

T1_START=$(date +%s%N)
RESP1=$(curl -s -X POST "$BRAIN_URL/see" | jq -r '.reply')
T1_END=$(date +%s%N)
T1_DURATION=$(echo "scale=2; ($T1_END - $T1_START) / 1000000" | bc)

echo "✓ 場景 1 回覆："
echo "  $RESP1"
echo "  耗時：${T1_DURATION}ms"
echo "" >> "$LOGFILE"
echo "【場景 1：水瓶】" >> "$LOGFILE"
echo "回覆：$RESP1" >> "$LOGFILE"
echo "耗時：${T1_DURATION}ms" >> "$LOGFILE"

# 場景 2：書
echo ""
echo "▶ 場景 2/3 ▶▶▶ 請在鏡頭前放【一本書】，10秒後自動拍攝..."
for i in {10..1}; do
  echo -n "$i "
  sleep 1
done
echo ""
echo "📷 拍攝中..."

T2_START=$(date +%s%N)
RESP2=$(curl -s -X POST "$BRAIN_URL/ask" -H "Content-Type: application/json" -d '{"text":"前面有什麼","speak":false}' | jq -r '.reply')
T2_END=$(date +%s%N)
T2_DURATION=$(echo "scale=2; ($T2_END - $T2_START) / 1000000" | bc)

echo "✓ 場景 2 回覆："
echo "  $RESP2"
echo "  耗時：${T2_DURATION}ms"
echo "" >> "$LOGFILE"
echo "【場景 2：書】" >> "$LOGFILE"
echo "回覆：$RESP2" >> "$LOGFILE"
echo "耗時：${T2_DURATION}ms" >> "$LOGFILE"

# 場景 3：空場景或人臉
echo ""
echo "▶ 場景 3/3 ▶▶▶ 請在鏡頭前放【淨空或人臉】，10秒後自動拍攝..."
for i in {10..1}; do
  echo -n "$i "
  sleep 1
done
echo ""
echo "📷 拍攝中..."

T3_START=$(date +%s%N)
RESP3=$(curl -s -X POST "$BRAIN_URL/ask" -H "Content-Type: application/json" -d '{"text":"仔細描述一下","speak":false}' | jq -r '.reply')
T3_END=$(date +%s%N)
T3_DURATION=$(echo "scale=2; ($T3_END - $T3_START) / 1000000" | bc)

echo "✓ 場景 3 回覆："
echo "  $RESP3"
echo "  耗時：${T3_DURATION}ms"
echo "" >> "$LOGFILE"
echo "【場景 3：淨空或人臉】" >> "$LOGFILE"
echo "回覆：$RESP3" >> "$LOGFILE"
echo "耗時：${T3_DURATION}ms" >> "$LOGFILE"

# 記憶體和性能指標
echo ""
echo "=== 性能指標 ==="
MEM_BRAIN=$(docker stats --no-stream robotcar-brain-1 2>/dev/null | tail -1 | awk '{print $7}')
MEM_OLLAMA=$(docker stats --no-stream robotcar-ollama-new-1 2>/dev/null | tail -1 | awk '{print $7}')

echo "brain 容器記憶體：$MEM_BRAIN"
echo "ollama 容器記憶體：$MEM_OLLAMA"
echo "" >> "$LOGFILE"
echo "=== 性能指標 ===" >> "$LOGFILE"
echo "場景 1 耗時：${T1_DURATION}ms" >> "$LOGFILE"
echo "場景 2 耗時：${T2_DURATION}ms" >> "$LOGFILE"
echo "場景 3 耗時：${T3_DURATION}ms" >> "$LOGFILE"
echo "平均耗時：$(echo "scale=2; ($T1_DURATION + $T2_DURATION + $T3_DURATION) / 3" | bc)ms" >> "$LOGFILE"
echo "brain 容器記憶體：$MEM_BRAIN" >> "$LOGFILE"
echo "ollama 容器記憶體：$MEM_OLLAMA" >> "$LOGFILE"

echo ""
echo "=== 測試完成 ==="
echo "✅ 三景測試完成，結果已保存到：$LOGFILE"
cat "$LOGFILE"
