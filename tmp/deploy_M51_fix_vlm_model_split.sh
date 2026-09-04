#!/bin/bash
# ============================================================
# M51：修「兩套 VLM 設定各自為政」的架構問題
#
#   發現（讀 GitHub 上的原始碼直接找到的，不是猜的）：
#   - modes.py 的 vlm_model（M46～M50 這幾輪一直在調的那個）只管
#     「切到觀察模式時，GPU 要不要預先幫你把哪顆模型載好」。
#   - 但「觀察模式詳細描述」按下去，真正打的是 vision.html →
#     /api/vision/describe → brain /see → vision/server.py 的
#     /capture，而 vision/server.py 有自己獨立的 VLM_MODEL 環境
#     變數（docker-compose.yml 預設 llava），跟 modes.py 完全是
#     兩條不相通的線。
#   - 也就是說，就算 modes.py 設成 moondream，實際按「詳細描述」
#     時 vision/server.py 還是在問 ollama 要 llava——這也可能是
#     先前 GPU 反覆出狀況的原因之一（兩套設定要不同模型互相打架）。
#
#   另外發現：brain/server.py 早就有完整的「VLM 英文描述 → qwen
#   2.5:3b 翻譯 → OpenCC 簡轉繁（s2twp，台灣用語）」生產線，M50
#   用 raw curl 直接打 ollama 時繞過了這條線，所以看到的簡體字問題
#   在真正的 /see 端點其實已經被修好了——不需要再另外修。
#
#   這次做的事：
#   1. 把 vision/server.py 實際使用的 VLM_MODEL 統一設成 moondream
#      （.env 設定＋docker-compose.yml 的預設值一起改，兩套設定
#      從此指向同一顆模型）。
#   2. modes.py 的 vlm_model 覆寫也同步設成 moondream（M50 已經設過，
#      這裡確認一致）。
#   3. 重建 vision 容器（它是用 build: 出來的 image，不是掛載檔案，
#      改環境變數要重建才會生效，不是單純 restart）。
#   4. 真正走生產路徑測試——不是 raw curl 打 ollama，是打
#      /api/vision/describe（跟按網頁上「詳細描述」按鈕完全一樣的
#      路徑），看真實的 reply 內容（已經過 OpenCC 轉繁體）。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
echo "== [1/8] 備份 .env、docker-compose.yml =="
cp -v .env ".env.bak.$TS" 2>/dev/null || echo "（.env 目前不存在，等一下會新建）"
cp -v docker-compose.yml "docker-compose.yml.bak.$TS"

echo "== [2/8] .env 裡設定 VLM_MODEL=moondream（沒有就新增，有就取代）=="
touch .env
if grep -q "^VLM_MODEL=" .env; then
  sed -i 's/^VLM_MODEL=.*/VLM_MODEL=moondream/' .env
else
  echo "VLM_MODEL=moondream" >> .env
fi
grep "^VLM_MODEL=" .env

echo "== [3/8] docker-compose.yml 的預設值也從 llava 改成 moondream（給沒設 .env 的情況一個安全預設）=="
sed -i 's/VLM_MODEL=\${VLM_MODEL:-llava}/VLM_MODEL=${VLM_MODEL:-moondream}/' docker-compose.yml
grep "VLM_MODEL" docker-compose.yml

echo "== [4/8] 確認 .gitignore 有排除 .env（不該把密鑰或本機設定提交上去）=="
grep -q "^\.env$" .gitignore && echo ".env 已在 .gitignore 裡，安全" || echo "⚠️ .env 沒有被 .gitignore 排除，先手動確認一下，不要直接 git add .env"

echo "== [5/8] 重建 vision 容器（build 出來的 image，改環境變數要重建）=="
docker compose build vision
docker compose up -d vision
sleep 5
docker compose ps vision

echo "== [6/8] 取帳密，同步 modes.py 的 vlm_model 覆寫（確保跟 vision 服務一致）=="
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode/config -H "Content-Type: application/json" -d '{"vlm_model":"moondream"}'
echo ""

echo "== [7/8] 真正走生產路徑測試：切到觀察模式，再打 /api/vision/describe（跟網頁按鈕一模一樣的路徑）=="
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"observe"}'
echo " ← 切到 observe"
sleep 15
echo "--- 切換後 GPU 狀態 ---"
curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu
echo ""
echo "--- 呼叫 /api/vision/describe（原始完整 JSON 回應）---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/vision/describe --max-time 60
echo ""
echo "--- 描述後再查一次 GPU 狀態 ---"
curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu
echo ""
echo "--- 收工前切回 manage ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""
unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [8/8] git commit + push =="
git add docker-compose.yml
git status --short
git commit -m "M51: 統一 VLM 模型設定，修 modes.py 與 vision/server.py 各自為政的問題

- docker-compose.yml：vision 服務的 VLM_MODEL 預設值從 llava 改
  moondream（llava 在這張卡上推理時 VRAM 不夠會崩，見 M49/M50
  的孤立測試證據）
- 根因：acoustic_app/modes.py 的 vlm_model（控制模式切換時 GPU
  預載哪顆模型）跟 vision/server.py 的 VLM_MODEL（控制 /capture
  實際問 ollama 要哪顆模型）過去是兩條不相通的設定，這次統一
- .env 同步設定 VLM_MODEL=moondream（本機檔案，不進版控）

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"

echo "--- push ---"
git push origin jn1-work
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git ls-remote origin jn1-work | awk '{print $1}')
echo "本地 HEAD: $LOCAL_HEAD"
echo "遠端 HEAD: $REMOTE_HEAD"
[ "$LOCAL_HEAD" = "$REMOTE_HEAD" ] && echo "✅ push 確認成功" || echo "❌ push 沒有真的成功，回報這兩行給我"

echo ""
echo "############################################################"
echo "M51 完成。請把 [7/8] 的『/api/vision/describe 原始完整 JSON"
echo "回應』整段貼給我——這是真正生產路徑的結果（已經過 OpenCC 轉"
echo "繁體），我要看 reply 欄位的中文內容品質，才能判斷這樣夠不夠"
echo "用，還是真的需要接雲端 Gemini 的圖片描述。"
echo "############################################################"
