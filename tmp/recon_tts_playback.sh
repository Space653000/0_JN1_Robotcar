#!/bin/bash
# ============================================================
# 偵查（不改任何檔案）：M53 測試時出現的 TTS "Connection failure:
# Access denied" 到底有沒有影響真實播放。
#
# 判斷邏輯：
#   wav 檔案已經生成（/data/logs/tts_1788532628274.wav），設計上
#   host 端的 jn1-tts-player 背景服務會輪詢 data/logs/tts_*.wav
#   並用 host 的 paplay 播出來——這條路徑理論上跟 tts 容器自己回報
#   的 play_error 是兩回事。這裡直接查證，不用猜的。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

echo "== 1. 那個 wav 檔案還在不在、多大 =="
ls -la data/logs/tts_1788532628274.wav 2>&1 || echo "（檔案不存在，可能已被清理，找目前最新的幾個 wav 看看）"
echo ""
echo "--- 最新的幾個 tts wav 檔案 ---"
ls -lat data/logs/tts_*.wav 2>&1 | head -5

echo ""
echo "== 2. host 端 jn1-tts-player 服務狀態 =="
systemctl --user status jn1-tts-player --no-pager -l | head -15

echo ""
echo "== 3. jn1-tts-player 最近的日誌（有沒有處理過這個檔案、有沒有真的呼叫 paplay）=="
journalctl --user -u jn1-tts-player --no-pager -n 60 2>&1

echo ""
echo "== 4. tts 服務（容器內）/say 端點的原始碼，看 play_error 這個訊息從哪裡來的 =="
grep -rn "Connection failure\|Access denied\|def say\|paplay\|pulse" src/tts/server.py 2>/dev/null | head -30

echo ""
echo "== 5. tts 容器目前的環境變數（有沒有意外掛了 PULSE_SERVER 之類，導致容器自己也想直接播放）=="
docker compose exec tts env 2>&1 | grep -i "pulse\|audio" || echo "（沒有 PULSE 相關環境變數，或 exec 失敗）"

echo ""
echo "############################################################"
echo "這一步不改任何東西。麻煩把上面 1~5 的原始輸出整段貼給我，"
echo "我看過之後才能判斷：這是無害的多餘錯誤，還是真的沒聲音。"
echo "############################################################"
