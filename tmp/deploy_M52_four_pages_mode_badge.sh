#!/bin/bash
# ============================================================
# M52：四頁（系統儀表板／聲學即時／視覺即時／助手即時）接上
#       「目前運轉模式」小標籤——步驟3的第一刀
#
#   原則（照 Stephen 的要求）：
#   - 只加，不刪、不改任何既有功能。
#   - 我已經先讀過 GitHub 上這四個檔案的實際內容再動手，避免用猜的
#     錨點或撞到既有的 id（例如 index.html 裡本來就有一個
#     id="modeBadge" 是用來顯示「示範資料/真實資料」的，跟五模式
#     無關——這次新加的標籤改用 id="jn1AttnMode"，完全不會撞到）。
#   - 每個檔案改之前先備份；改完用 grep 同時確認「新標籤加進去了」
#     和「舊的關鍵功能還在」，兩者都要過才算數。
#
#   這一輪先做「顯示目前模式」（點一下可以跳去 /manage 切換），
#   還沒做「隨模式調整行為」（例如觀察模式時視覺頻率變化）——那個
#   涉及改動既有的輪詢/顯示邏輯，風險比較高，等這一步先穩定上線、
#   確認四頁都正常之後再做，避免一次改太多不好抓問題。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
DASH="jn1_dashboard.html"
ACOU="acoustic_app/static/index.html"
VIS="acoustic_app/static/vision.html"
ASST="acoustic_app/static/assistant.html"

echo "== [1/6] 備份四個檔案 =="
cp -v "$DASH" "$DASH.bak.$TS"
cp -v "$ACOU" "$ACOU.bak.$TS"
cp -v "$VIS" "$VIS.bak.$TS"
cp -v "$ASST" "$ASST.bak.$TS"

echo "== [2/6] 錨點檢查（每個錨點都要「剛好出現一次」才會插入，不然直接停）=="
python3 <<'PYCHECK'
import sys

checks = [
    ("jn1_dashboard.html",
     '<button onclick="jn1SpeakStatus()"'),
    ("acoustic_app/static/index.html",
     '<span id="modeBadge" class="badge demo"><span class="dot"></span>示範資料 DEMO</span>'),
    ("acoustic_app/static/vision.html",
     '<span class="badge" id="badge">連線中…</span>'),
    ("acoustic_app/static/assistant.html",
     '<span class="spacer"></span>'),
]
ok = True
for path, anchor in checks:
    with open(path, encoding="utf-8") as f:
        src = f.read()
    n = src.count(anchor)
    status = "OK" if n == 1 else "FAIL"
    if n != 1:
        ok = False
    print(f"[{status}] {path}: 錨點出現 {n} 次")
if not ok:
    print("有錨點不是剛好出現一次，停止，不動任何檔案，回報這個結果給我")
    sys.exit(1)
print("全部錨點確認 OK，可以插入")
PYCHECK

echo "== [3/6] 插入四頁的模式標籤（id=jn1AttnMode，不會撞到既有任何 id）=="
python3 <<'PYEOF'
# ---------- 共用的 icon 對照 + 刷新函式（四頁共同邏輯，各自貼一份）----------
SHARED_SCRIPT = """
<script>
const JN1_ATTN_ICON={manage:"🎛️",chat:"🗣️",observe:"👁️",patrol:"🏃",standby:"😴"};
async function jn1RefreshAttnMode(){
  try{
    const r=await fetch('/api/mode');const d=await r.json();
    const el=document.getElementById('jn1AttnMode');
    if(el&&d&&d.all&&d.mode&&d.all[d.mode]){el.textContent=(JN1_ATTN_ICON[d.mode]||'\\u25CF')+' '+d.all[d.mode].label;}
  }catch(e){}
}
jn1RefreshAttnMode();setInterval(jn1RefreshAttnMode,15000);
</script>
"""

def replace_once(path, anchor, insert_after):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert src.count(anchor) == 1, f"{path}: anchor count != 1"
    idx = src.find(anchor) + len(anchor)
    new_src = src[:idx] + insert_after + src[idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)
    print(f"寫入完成：{path}（新檔案長度 {len(new_src)} 字元，原本 {len(src)}）")

# ---------- 1. jn1_dashboard.html：append 在檔案最後（跟 TTS 按鈕同樣的加法）----------
with open("jn1_dashboard.html", encoding="utf-8") as f:
    dash_src = f.read()
dash_badge = (
    '\n<a href="/manage" id="jn1AttnMode" style="position:fixed;left:16px;bottom:16px;'
    'z-index:9999;background:var(--panel);color:var(--ink);border:1px solid var(--line);'
    'border-radius:20px;padding:8px 14px;font:600 13px system-ui;box-shadow:var(--shadow);'
    'text-decoration:none;cursor:pointer" '
    'title="目前運轉模式，點一下前往管理（開發）駕駛艙">讀取中…</a>\n'
    + SHARED_SCRIPT
)
with open("jn1_dashboard.html", "w", encoding="utf-8") as f:
    f.write(dash_src + dash_badge)
print("寫入完成：jn1_dashboard.html（append 到檔尾）")

# ---------- 2. acoustic index.html：插在既有 modeBadge 之後（同一個 header 裡）----------
replace_once(
    "acoustic_app/static/index.html",
    '<span id="modeBadge" class="badge demo"><span class="dot"></span>示範資料 DEMO</span>',
    '\n    <a href="/manage" class="badge" id="jn1AttnMode" style="text-decoration:none;cursor:pointer" '
    'title="目前運轉模式，點一下前往管理（開發）駕駛艙">讀取中…</a>'
)
with open("acoustic_app/static/index.html", "a", encoding="utf-8") as f:
    f.write(SHARED_SCRIPT)
print("index.html 的 script 已 append 到檔尾")

# ---------- 3. vision.html：插在既有 badge 之後（同一個 header 裡）----------
replace_once(
    "acoustic_app/static/vision.html",
    '<span class="badge" id="badge">連線中…</span>',
    '\n  <a href="/manage" class="badge" id="jn1AttnMode" style="text-decoration:none;cursor:pointer" '
    'title="目前運轉模式，點一下前往管理（開發）駕駛艙">讀取中…</a>'
)
with open("acoustic_app/static/vision.html", "a", encoding="utf-8") as f:
    f.write(SHARED_SCRIPT)
print("vision.html 的 script 已 append 到檔尾")

# ---------- 4. assistant.html：插在 header 的 spacer 之後 ----------
replace_once(
    "acoustic_app/static/assistant.html",
    '<span class="spacer"></span>',
    '\n    <a href="/manage" id="jn1AttnMode" style="text-decoration:none;cursor:pointer;font:600 12px system-ui;'
    'padding:4px 10px;border-radius:20px;background:var(--panel2);border:1px solid var(--line);color:var(--ink2)" '
    'title="目前運轉模式，點一下前往管理（開發）駕駛艙">讀取中…</a>'
)
with open("acoustic_app/static/assistant.html", "a", encoding="utf-8") as f:
    f.write(SHARED_SCRIPT)
print("assistant.html 的 script 已 append 到檔尾")
PYEOF

echo "== [4/6] 靜態檔案，不需要重啟服務（純 HTML/JS），但重新整理瀏覽器快取的話，逼一下 jn1-web 也無妨 =="
systemctl --user restart jn1-web
sleep 3

echo "== [5/6] 取帳密，驗證：新標籤有加進去、原本的關鍵功能也都還在 =="
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

check_page () {
  local name="$1" path="$2"
  echo "--- $name ($path) ---"
  local code=$(curl -sS $AUTH -o /tmp/jn1_check_$$.html -w "%{http_code}" "http://127.0.0.1:8011$path")
  echo "HTTP 狀態：$code"
  echo -n "新標籤 jn1AttnMode 出現次數："; grep -c "jn1AttnMode" /tmp/jn1_check_$$.html || true
  rm -f /tmp/jn1_check_$$.html
}

check_page "系統儀表板" "/dashboard"
echo -n "舊功能 themeToggle 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/dashboard" | grep -c "themeToggle" || true
echo -n "舊功能 唸系統狀態 按鈕還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/dashboard" | grep -c "jn1SpeakStatus" || true

check_page "聲學即時" "/acoustic"
echo -n "舊功能 modeBadge(示範/真實資料) 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/acoustic" | grep -c 'id="modeBadge"' || true
echo -n "舊功能 校準按鈕 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/acoustic" | grep -c "校准正前方\|校準正前方" || true

check_page "視覺即時" "/vision"
echo -n "舊功能 btnSpeak(唸出描述) 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/vision" | grep -c "btnSpeak" || true
echo -n "舊功能 describe() 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/vision" | grep -c "function describe" || true

check_page "助手即時" "/assistant"
echo -n "舊功能 quick(常用問題列) 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/assistant" | grep -c 'id="quick"' || true
echo -n "舊功能 assistant/ask 呼叫 還在嗎："; curl -sS $AUTH "http://127.0.0.1:8011/assistant" | grep -c "/api/assistant/ask" || true

unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [6/6] git commit + push =="
git add jn1_dashboard.html acoustic_app/static/index.html acoustic_app/static/vision.html acoustic_app/static/assistant.html
git status --short
git commit -m "M52: 四頁（儀表板/聲學/視覺/助手）加上目前運轉模式標籤

- 純加法：每頁加一個 id=jn1AttnMode 的小標籤，每 15 秒讀 /api/mode
  顯示目前是哪個模式，點一下跳去 /manage 切換
- 刻意避開既有 id（例如 index.html 原本就有 id=modeBadge 是示範/
  真實資料指示，跟五模式無關，兩者並存不衝突）
- 不動任何既有功能、既有資料/歷程，部署腳本有逐項 grep 驗證舊功能
  還在（themeToggle、jn1SpeakStatus、原本的 modeBadge、校準按鈕、
  btnSpeak、describe()、quick 常用問題列、/api/assistant/ask）
- 這一輪只做「顯示模式」，還沒做「隨模式調整行為」（風險較高，
  留到下一輪，確認這一步穩定後再做）

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
echo "M52 完成。請把 [5/6] 那一整段驗證輸出貼給我——我要看四頁的"
echo "HTTP 狀態、新標籤出現次數（要是 1）、以及每個舊功能的 grep"
echo "結果（要 >=1，代表沒被刪掉）。全部過我才會說這步真的做完。"
echo "############################################################"
