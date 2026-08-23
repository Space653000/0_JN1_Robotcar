#!/bin/bash
# 一鍵推送到 GitHub：/home/jetson/0_JN1_Robotcar -> Space653000/0_JN1_Robotcar
# 用法：直接執行本檔即可（./push.sh 或 bash push.sh）
set -e
cd "$(dirname "$0")"

if [ -n "$(git status --porcelain)" ]; then
    git add -A
    ts=$(date "+%Y-%m-%d %H:%M:%S")
    git commit -m "自動同步 ${ts}"
    echo "✅ 已建立新 commit"
else
    echo "ℹ️  沒有變更，跳過 commit"
fi

git push origin main
echo "✅ 已推送到 https://github.com/Space653000/0_JN1_Robotcar"
