#!/bin/bash
# ============================================================
# 驗證區（在 M46 部署腳本跑完、確認 server.py 語法 OK 之後再跑這個）
# 目的：
#   A) 真的把 M45(a157c43) + M46 推上 GitHub，並用「兩邊 commit id 是否相同」證明，
#      不是看 git 自己印的「提交完成」字樣。
#   B) 用「完全卸掉 qwen 之後，直接叫 llava 常駐，再查 /api/ps」這個孤立測試，
#      確定 llava 到底塞不塞得進 GPU——GPU=[] 不算數，一定要看到
#      裡面真的出現 "llava" 這個名字才算過。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

echo "########## A. 真的 push，並比對兩邊 commit id ##########"
echo "--- push 前，本地 HEAD ---"
git log -1 --format="%H %s"

echo "--- git push origin jn1-work ---"
git push origin jn1-work

echo "--- push 後，本地 HEAD ---"
LOCAL_HEAD=$(git rev-parse HEAD)
echo "$LOCAL_HEAD"

echo "--- 遠端 jn1-work 現在指到哪（git ls-remote，不是本地快取）---"
REMOTE_HEAD=$(git ls-remote origin jn1-work | awk '{print $1}')
echo "$REMOTE_HEAD"

if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
  echo "✅ 兩邊 commit id 完全一致，push 是真的成功。"
else
  echo "❌ 兩邊不一致！本地=$LOCAL_HEAD 遠端=$REMOTE_HEAD ——push 沒有真的成功，回報這兩行給我。"
fi

echo ""
echo "########## B. LLAVA 孤立測試（qwen 完全讓位後，llava 真的塞得進去嗎）##########"

echo "--- 步驟1：強制卸載 qwen2.5:3b ---"
curl -sS http://127.0.0.1:11434/api/generate -d '{"model":"qwen2.5:3b","keep_alive":0,"prompt":""}'
echo ""

echo "--- 步驟2：確認 GPU 已清空（原始 /api/ps）---"
curl -sS http://127.0.0.1:11434/api/ps
echo ""

echo "--- 步驟3：直接叫 llava 常駐（keep_alive:-1），這步可能要等 10~60 秒 ---"
curl -sS http://127.0.0.1:11434/api/generate -d '{"model":"llava","keep_alive":-1,"prompt":"hi","stream":false}'
echo ""

echo "--- 步驟4：再查一次 /api/ps，這是最終判定依據（原始輸出）---"
curl -sS http://127.0.0.1:11434/api/ps
echo ""

echo "############################################################"
echo "判定規則（我會照這個唸，不是照你自己的結論）："
echo "  - 步驟4的 JSON 裡，models 陣列裡如果看得到 name 含 \"llava\" → 塞得進去，觀察模式定案用 llava。"
echo "  - 如果步驟3就回傳錯誤（例如 out of memory / 500），或步驟4 models 是空的 → 塞不進去，"
echo "    観察模式改用小型 VLM（例如 moondream，約 1.7GB），我再給你切換指令。"
echo "  請把「步驟3」和「步驟4」的完整原始輸出貼給我，我自己判斷，不要用你自己的話總結。"
echo "############################################################"
