#!/bin/bash
# ============================================================
# M53：補收尾——/api/vision/describe 逾時 30秒→90秒（先前已判定
#       原因、已取得同意，這次真的動手改並用真實路徑驗證）
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
echo "== [1/6] 備份 acoustic_app/server.py =="
cp -v acoustic_app/server.py "acoustic_app/server.py.bak.$TS"

echo "== [2/6] 錨點檢查（要剛好出現一次才動手）=="
grep -c 'async with httpx.AsyncClient(timeout=30.0) as c:' acoustic_app/server.py

echo "== [3/6] 修改逾時 30.0 -> 90.0（只改 /api/vision/describe 這一個路由，不動其他）=="
python3 <<'PYEOF'
path = "acoustic_app/server.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

anchor_func = '@app.post("/api/vision/describe")\nasync def vision_describe():'
old_line = 'async with httpx.AsyncClient(timeout=30.0) as c:'
new_line = 'async with httpx.AsyncClient(timeout=90.0) as c:  # M53：實測完整鏈路約39秒，30秒不夠'

idx_func = src.find(anchor_func)
assert idx_func != -1, "找不到 vision_describe 函式，停止"

# 只在這個函式定義之後的第一個 timeout=30.0 出現處替換，不影響其他路由
idx_target = src.find(old_line, idx_func)
assert idx_target != -1, "在 vision_describe 函式裡找不到 timeout=30.0，停止"

new_src = src[:idx_target] + new_line + src[idx_target + len(old_line):]
assert new_src.count('timeout=30.0') == src.count('timeout=30.0') - 1, "應該剛好少一個 timeout=30.0，數量對不上，停止不寫檔"

with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)
print("修改完成")
PYEOF

echo "== [4/6] 語法檢查 =="
python3 -c "import ast; ast.parse(open('acoustic_app/server.py', encoding='utf-8').read())" && echo "server.py 語法 OK" || { echo "❌ 語法錯誤！立刻回復備份：cp acoustic_app/server.py.bak.$TS acoustic_app/server.py"; exit 1; }

echo "== [5/6] 重啟 jn1-web，走真實路徑驗證（跟按網頁『詳細描述』按鈕一樣的路徑）=="
systemctl --user restart jn1-web
sleep 3

set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"observe"}'
echo " ← 切到 observe"
sleep 15

echo "--- 開始計時，呼叫 /api/vision/describe ---"
START=$(date +%s)
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/vision/describe --max-time 100
END=$(date +%s)
echo ""
echo "耗時：$((END-START)) 秒（逾時上限現在是90秒）"

echo "--- 收工前切回 manage ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""
unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [6/6] git commit + push =="
git add acoustic_app/server.py
git status --short
git commit -m "M53: /api/vision/describe 逾時 30秒→90秒

- 根因（M51已定位）：brain /see 完整鏈路（卸載qwen→moondream推理
  →冷重載qwen翻譯→OpenCC簡轉繁）實測約39.2秒，30秒逾時不夠
- 只改這一個路由的 timeout，其他路由不動
- 這次用真實路徑（切observe→呼叫/api/vision/describe）計時驗證

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
echo "M53 完成。請把 [5/6] 的『耗時：X秒』還有 /api/vision/describe"
echo "的原始 JSON 回應貼給我——確認真的在90秒內拿到完整、有意義的"
echo "reply，觀察模式的『詳細描述』才算真正打通、收尾。"
echo "############################################################"
