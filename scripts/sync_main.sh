#!/bin/bash
# M59.5：雙分支同步政策。
#
# jn1-work 是唯一工作分支；main 只用來給外部審查看最新狀態。
# main 落後是異常狀態，不是可接受的常態——2026-09-05 雲端規劃時
# 誤判 main 落後代表 M45-M58 遺失（見 J4012_AI車_目標與架構_v2.1
# 的「修正9」與 v2.2 的更正），實際上只是沒人同步 main。
#
# 用法：每次 `git push origin jn1-work` 之後，緊接著執行這支。
set -e
cd "$(git rev-parse --show-toplevel)"

CURRENT=$(git branch --show-current)
if [ "$CURRENT" != "jn1-work" ]; then
    echo "❌ 目前不在 jn1-work 分支（在 $CURRENT），先切回去再跑這支"
    exit 1
fi

git fetch origin
BEHIND=$(git rev-list --count origin/main..jn1-work)
if [ "$BEHIND" = "0" ]; then
    echo "main 已經跟 jn1-work 一致，不需要同步"
    exit 0
fi

echo "main 落後 jn1-work $BEHIND 個 commit，開始同步..."
git checkout main
git merge --ff-only jn1-work
git push origin main
git checkout jn1-work

echo "✅ 同步完成"
git rev-parse main jn1-work
