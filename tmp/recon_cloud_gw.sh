#!/bin/bash
# ============================================================
# M51 前置偵查：不改任何檔案，只印出現有 cloud-gw 呼叫方式
# 目的：在寫「觀察模式接雲端 Gemini」之前，先看真實的 API 長怎樣，
#       不要用猜的欄位名稱去串接，猜錯了又要重來一輪。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

echo "== 1. 搜尋原始碼裡跟 cloud-gw / 8010 / gemini 有關的地方 =="
grep -rn "cloud-gw\|CLOUD_GW\|8010\|gemini\|Gemini" \
  --include="*.py" --include="*.yml" --include="*.yaml" --include="*.env*" \
  acoustic_app/ src/ docker/ docker-compose.yml 2>/dev/null | grep -v ".bak."

echo ""
echo "== 2. 如果 docker-compose.yml 有 cloud-gw 服務定義，印出來 =="
grep -A 15 "cloud-gw:" docker-compose.yml 2>/dev/null || echo "（docker-compose.yml 裡沒找到 cloud-gw: 這個 service 名稱，可能叫別的名字，上面第1步的結果為準）"

echo ""
echo "== 3. 如果有獨立的 cloud-gw server 原始碼檔案，找出來並印出前 80 行 =="
CLOUD_GW_FILE=$(grep -rl "cloud" --include="*.py" src/ 2>/dev/null | grep -i "gw\|gateway\|cloud" | head -1)
if [ -n "$CLOUD_GW_FILE" ]; then
  echo "找到檔案：$CLOUD_GW_FILE"
  head -80 "$CLOUD_GW_FILE"
else
  echo "沒有自動找到明顯的 cloud gateway 原始碼檔案，麻煩人工看一下 src/ 底下的資料夾結構："
  find src/ -maxdepth 2 -type d 2>/dev/null
fi

echo ""
echo "== 4. 直接問 cloud-gw 服務本身有沒有回應、有沒有內建的說明（原始輸出）=="
curl -sS --max-time 5 http://127.0.0.1:8010/ 2>&1 || echo "（8010 根目錄沒有回應或逾時，不代表服務有問題，只是這條路徑可能沒定義）"
echo ""
curl -sS --max-time 5 http://127.0.0.1:8010/health 2>&1 || echo "（/health 沒有回應，同上）"
echo ""

echo "############################################################"
echo "這一步不改任何檔案。麻煩把上面 1~4 的原始輸出整段貼給我，"
echo "我看過真實的 API 之後才動手寫觀察模式接雲端的程式碼。"
echo "############################################################"
