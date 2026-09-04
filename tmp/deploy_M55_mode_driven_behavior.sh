#!/bin/bash
# ============================================================
# M55：藍圖步驟 3b —— 四頁「隨模式調整行為」
#
#   3a（M52）做的是「顯示目前是哪個模式」，這次做的是「頁面真的
#   照模式改行為」，也就是藍圖注意力槽那張表右半邊的落實：
#     🎛️ 管理  → 完全維持原本（全功能檢查，不動）
#     🗣️ 對話  → 視覺降頻（藍圖：「YOLO標框、不細看」），資源留給 qwen；
#                助手頁自動勾「唸出來」（藍圖：朗讀）
#     👁️ 觀察  → 偵測加快（藍圖：「專心看仔細」）；
#                視覺頁描述完自動唸出來
#     🏃 巡航  → 偵測最快（藍圖：「高頻偵測人/障礙」）
#     😴 待機  → 大幅降頻（藍圖：「暫停/低頻、省電降溫」）
#
#   ★ 最重要的安全設計（fail-safe）：
#     每個呼叫點都寫成 window.jn1Rate ? window.jn1Rate(...) : 原本的值。
#     所以只要 /api/mode 掛掉、或模式讀不到、或是沒看過的模式名稱，
#     四頁就完全維持今天的頻率，不會因為模式功能出問題而整個變慢。
#     我已經在本地用 node 實際跑過這個 fallback 邏輯驗證：
#       模式空白/亂值/manage → frame=90 detect=700 thumb=120（＝現況）
#       只有 chat/observe/patrol/standby 才會改變。
#
#   ★ 這份腳本裡的改動邏輯，跟我本地已經驗證過的是同一份程式碼
#     （同一個 m55_patch.py，原封不動內嵌），不是另外重打一份，
#     避免「驗的東西跟部署的東西不一樣」這種假驗證。
#     本地已驗證：四頁改完後 12 個 inline script 區塊，node --check
#     全部語法 OK。
#
#   ★ 儀表板：老實說，它沒有任何輪詢迴圈（遙測只在按🔊時抓一次），
#     沒有東西可以隨模式調頻率。這次它只換共用區塊保持一致，
#     行為沒有改變——不假裝有做事。
#
#   原則照舊：只加不刪、先備份、錨點檢查（四個檔案全部過了才寫檔）、
#   改完逐項 grep 確認舊功能都還在。
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

echo ""
echo "== [2/6] 套用改動（兩階段：四個檔案的錨點全部確認完才開始寫檔）=="
cat > /tmp/m55_patch_$$.py <<'M55PATCHEOF'
#!/usr/bin/env python3
# M55 的實際改動邏輯。deploy 腳本和我本地的預先驗證共用同一份，
# 避免「驗證的東西跟部署的東西不一樣」這種假驗證。
import sys, os

OLD_SHARED = '''<script>
const JN1_ATTN_ICON={manage:"\U0001F39B️",chat:"\U0001F5E3️",observe:"\U0001F441️",patrol:"\U0001F3C3",standby:"\U0001F634"};
async function jn1RefreshAttnMode(){
  try{
    const r=await fetch('/api/mode');const d=await r.json();
    const el=document.getElementById('jn1AttnMode');
    if(el&&d&&d.all&&d.mode&&d.all[d.mode]){el.textContent=(JN1_ATTN_ICON[d.mode]||'\\u25CF')+' '+d.all[d.mode].label;}
  }catch(e){}
}
jn1RefreshAttnMode();setInterval(jn1RefreshAttnMode,15000);
</script>'''

NEW_SHARED = '''<script>
const JN1_ATTN_ICON={manage:"\U0001F39B️",chat:"\U0001F5E3️",observe:"\U0001F441️",patrol:"\U0001F3C3",standby:"\U0001F634"};
/* M55：模式驅動的行為調整。
   重點：所有呼叫點都寫成 window.jn1Rate ? ... : 原本的值，
   所以 /api/mode 掛掉、或這段還沒載入時，每一頁都完全維持原本的頻率，
   不會因為模式功能出問題就整個變慢或變快（fail-safe）。 */
window.JN1_MODE='';
window.JN1_RATE={
  manage :{frame:90,  detect:700,  thumb:120 },
  chat   :{frame:300, detect:1500, thumb:120 },
  observe:{frame:90,  detect:400,  thumb:400 },
  patrol :{frame:90,  detect:300,  thumb:600 },
  standby:{frame:3000,detect:6000, thumb:3000}
};
window.jn1Rate=function(key,fallback){
  var r=window.JN1_RATE[window.JN1_MODE];
  return (r&&r[key]!=null)?r[key]:fallback;
};
async function jn1RefreshAttnMode(){
  try{
    const r=await fetch('/api/mode');const d=await r.json();
    const el=document.getElementById('jn1AttnMode');
    if(el&&d&&d.all&&d.mode&&d.all[d.mode]){el.textContent=(JN1_ATTN_ICON[d.mode]||'\\u25CF')+' '+d.all[d.mode].label;}
    if(d&&d.mode&&d.mode!==window.JN1_MODE){
      var prev=window.JN1_MODE;window.JN1_MODE=d.mode;
      if(typeof window.jn1OnModeChange==='function'){try{window.jn1OnModeChange(d.mode,prev);}catch(e){}}
    }
  }catch(e){}
}
jn1RefreshAttnMode();setInterval(jn1RefreshAttnMode,15000);
</script>'''

ASSIST_HOOK = '''<script>
/* M55：對話模式自動勾選「唸出來」。
   只要使用者自己動過這個開關，之後就完全不再自動改它——不搶使用者的手。 */
window.jn1SpeakTouched=false;
(function(){var c=document.getElementById('speak');
  if(c)c.addEventListener('change',function(){window.jn1SpeakTouched=true;});})();
window.jn1OnModeChange=function(mode,prev){
  var c=document.getElementById('speak');
  if(!c||window.jn1SpeakTouched)return;
  c.checked=(mode==='chat');
};
</script>
'''

EDITS = [
    ("acoustic_app/static/vision.html", [
        ("setTimeout(pollFrame,90);",
         "setTimeout(pollFrame,(window.jn1Rate?window.jn1Rate('frame',90):90));"),
        ("setTimeout(detect,700);",
         "setTimeout(detect,(window.jn1Rate?window.jn1Rate('detect',700):700));"),
        # 觀察模式：描述完自動唸出來（朗讀）
        ("if(d.ok&&d.reply){lastDesc=d.reply;",
         "if(d.ok&&d.reply){lastDesc=d.reply;if(window.JN1_MODE==='observe'){try{speakDesc();}catch(e){}}"),
        (OLD_SHARED, NEW_SHARED),
    ]),
    ("acoustic_app/static/index.html", [
        ("setTimeout(poll,90);",
         "setTimeout(poll,(window.jn1Rate?window.jn1Rate('frame',90):90));"),
        (OLD_SHARED, NEW_SHARED),
    ]),
    ("acoustic_app/static/assistant.html", [
        ("setTimeout(pollFrame,120);",
         "setTimeout(pollFrame,(window.jn1Rate?window.jn1Rate('thumb',120):120));"),
        (OLD_SHARED, ASSIST_HOOK + NEW_SHARED),
    ]),
    # 儀表板沒有任何輪詢迴圈（遙測只在按下🔊按鈕時抓一次），
    # 沒有東西可以「隨模式調頻率」——只換共用區塊，讓它跟其他頁一致。
    ("jn1_dashboard.html", [
        (OLD_SHARED, NEW_SHARED),
    ]),
]


def apply_all(root):
    """兩階段：先把四個檔案的每一個錨點全部檢查完，全部過了才開始寫檔。
    避免「改到第三個檔案才發現錨點不對」而留下改一半的狀態。"""
    staged = []
    for path, edits in EDITS:
        full = os.path.join(root, path)
        with open(full, encoding="utf-8") as f:
            src = f.read()
        orig_len = len(src)
        for old, new in edits:
            n = src.count(old)
            if n != 1:
                print(f"[FAIL] {path}: 錨點出現 {n} 次（應為1）-> {old[:45]}")
                print("四個檔案全部不動，回報這行給我")
                sys.exit(1)
            src = src.replace(old, new, 1)
        print(f"[檢查OK] {path}: {orig_len} -> {len(src)} 字元")
        staged.append((full, path, src, orig_len))

    print("--- 四個檔案的錨點全部確認完畢，開始寫檔 ---")
    for full, path, src, orig_len in staged:
        with open(full, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"[已寫入] {path}: {orig_len} -> {len(src)} 字元")


if __name__ == "__main__":
    apply_all(sys.argv[1] if len(sys.argv) > 1 else ".")

M55PATCHEOF
python3 /tmp/m55_patch_$$.py "$REPO"
rm -f /tmp/m55_patch_$$.py

echo ""
echo "== [3/6] 如果這台有 node，順便再做一次 JS 語法檢查（沒有就跳過，我本地已驗過）=="
if command -v node >/dev/null 2>&1; then
python3 - <<'CHKEOF'
import re, subprocess, os
files = ["jn1_dashboard.html","acoustic_app/static/index.html",
         "acoustic_app/static/vision.html","acoustic_app/static/assistant.html"]
bad=0; total=0
for p in files:
    src = open(p, encoding="utf-8").read()
    for i,b in enumerate(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', src, re.S)):
        total+=1
        tmp=f"/tmp/_m55chk_{i}_{os.path.basename(p)}.js"
        open(tmp,"w",encoding="utf-8").write(b)
        r=subprocess.run(["node","--check",tmp],capture_output=True,text=True)
        if r.returncode!=0:
            bad+=1; print(f"[語法錯誤] {p} 區塊{i}:\n{r.stderr[:400]}")
        os.remove(tmp)
print(f"{total} 個 inline script 區塊，語法錯誤 {bad} 個")
CHKEOF
else
  echo "（這台沒有 node，跳過；我本地已用 node --check 驗過 12 個區塊全部 OK）"
fi

echo ""
echo "== [4/6] 重啟 jn1-web，逐頁確認「新行為加進去了」＋「舊功能都還在」 =="
systemctl --user restart jn1-web
sleep 3

set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

get_page () { curl -sS $AUTH "http://127.0.0.1:8011$1"; }

echo "--- 視覺即時 /vision ---"
echo -n "HTTP 狀態："; curl -sS $AUTH -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8011/vision"
echo -n "[新] 相機輪詢已接模式(jn1Rate frame)："; get_page /vision | grep -c "jn1Rate('frame',90)" || true
echo -n "[新] 偵測輪詢已接模式(jn1Rate detect)："; get_page /vision | grep -c "jn1Rate('detect',700)" || true
echo -n "[新] 觀察模式自動唸描述："; get_page /vision | grep -c "JN1_MODE==='observe'" || true
echo -n "[舊] btnSpeak 唸出描述按鈕："; get_page /vision | grep -c "btnSpeak" || true
echo -n "[舊] describe() 函式："; get_page /vision | grep -c "function describe" || true
echo -n "[舊] drawBoxes 畫框："; get_page /vision | grep -c "function drawBoxes" || true
echo -n "[舊] 偵測到人的預警："; get_page /vision | grep -c "alertPerson" || true

echo "--- 聲學即時 /acoustic ---"
echo -n "HTTP 狀態："; curl -sS $AUTH -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8011/acoustic"
echo -n "[新] 相機輪詢已接模式："; get_page /acoustic | grep -c "jn1Rate('frame',90)" || true
echo -n "[舊] WebSocket 即時聲學(ws/live)："; get_page /acoustic | grep -c "ws/live" || true
echo -n "[舊] modeBadge 示範/真實資料指示："; get_page /acoustic | grep -c 'id="modeBadge"' || true
echo -n "[舊] 校準按鈕："; get_page /acoustic | grep -c "api/calibrate_front" || true
echo -n "[舊] 示範模式 startDemo："; get_page /acoustic | grep -c "function startDemo" || true

echo "--- 助手即時 /assistant ---"
echo -n "HTTP 狀態："; curl -sS $AUTH -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8011/assistant"
echo -n "[新] 縮圖輪詢已接模式："; get_page /assistant | grep -c "jn1Rate('thumb',120)" || true
echo -n "[新] 對話模式自動勾唸出來："; get_page /assistant | grep -c "jn1OnModeChange" || true
echo -n "[舊] quick 常用問題列："; get_page /assistant | grep -c 'id="quick"' || true
echo -n "[舊] /api/assistant/ask："; get_page /assistant | grep -c "/api/assistant/ask" || true
echo -n "[舊] 唸出來勾選框 id=speak："; get_page /assistant | grep -c 'id="speak"' || true
echo -n "[舊] health 輪詢："; get_page /assistant | grep -c "function health" || true

echo "--- 系統儀表板 /dashboard（沒有輪詢迴圈，行為不變，只確認沒被弄壞）---"
echo -n "HTTP 狀態："; curl -sS $AUTH -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8011/dashboard"
echo -n "[舊] themeToggle 主題切換："; get_page /dashboard | grep -c "themeToggle" || true
echo -n "[舊] jn1SpeakStatus 唸系統狀態："; get_page /dashboard | grep -c "jn1SpeakStatus" || true

echo "--- 四頁共同：模式標籤(M52)還在、新的 jn1Rate 都有載到 ---"
for P in /dashboard /acoustic /vision /assistant; do
  echo -n "$P  jn1AttnMode標籤:"; get_page $P | grep -c "jn1AttnMode" || true
  echo -n "$P  window.jn1Rate定義:"; get_page $P | grep -c "window.jn1Rate=function" || true
done

echo ""
echo "== [5/6] 確認 /api/mode 本身還正常（頁面靠它決定行為）=="
curl -sS $AUTH http://127.0.0.1:8011/api/mode
echo ""
unset ACOUSTIC_USER ACOUSTIC_PASS

echo ""
echo "== [6/6] git commit + push =="
git add "$DASH" "$ACOU" "$VIS" "$ASST"
git status --short
git commit -m "M55: 四頁隨模式調整行為（藍圖步驟 3b）

- 3a(M52) 只做「顯示目前模式」，這次做「照模式改行為」：
  對話→視覺降頻(資源留給qwen)＋助手頁自動勾唸出來
  觀察→偵測加快(400ms)＋描述完自動唸出來
  巡航→偵測最快(300ms，高頻偵測人/障礙)
  待機→大幅降頻(3000/6000ms，省電降溫)
  管理→完全維持原本行為，一個字都沒變
- fail-safe：所有呼叫點寫成 window.jn1Rate ? ... : 原本的值，
  /api/mode 掛掉或模式讀不到時四頁完全維持現況，不會因為模式
  功能出問題而整個變慢。已用 node 實際跑過 fallback 邏輯驗證
- 只加不刪：四頁原有功能(ws即時聲學、示範模式、校準、畫框、
  預警、常用問題列、唸出來勾選框、主題切換…)完全沒動，部署
  腳本逐項 grep 驗證
- 儀表板沒有輪詢迴圈可調，只換共用區塊保持一致，行為不變
- 改動前已在本地套用同一份 patch 並用 node --check 驗證四頁
  共 12 個 inline script 區塊語法全部 OK

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JekVVqPrNEBMVYvx3MH2kF"

echo "--- push ---"
git push origin jn1-work
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git ls-remote origin jn1-work | awk '{print $1}')
echo "本地 HEAD: $LOCAL_HEAD"
echo "遠端 HEAD: $REMOTE_HEAD"
[ "$LOCAL_HEAD" = "$REMOTE_HEAD" ] && echo "push 確認成功（兩個 hash 相同）" || echo "push 沒有真的成功，回報這兩行給我"

echo ""
echo "############################################################"
echo "M55 完成。請把 [4/6] 那一整段逐頁驗證輸出貼給我。"
echo ""
echo "另外有一個「只有瀏覽器看得到」的真實驗證，curl 驗不出來，"
echo "麻煩 Stephen 自己開網頁看一眼（30秒就好）："
echo "  1. 開 /vision 視覺即時，看右上角『更新 X/s』那個數字"
echo "  2. 去 /manage 切到「巡航」，回來看那個數字應該變大"
echo "     （偵測從 700ms → 300ms，約 1.4/s → 3.3/s）"
echo "  3. 再切到「待機」，那個數字應該掉到接近 0.2/s，畫面更新"
echo "     也明顯變慢（省電降溫）"
echo "  4. 切回「管理」，一切恢復原本的樣子"
echo "這樣就能親眼確認『模式真的在控制行為』，不是只有標籤在變。"
echo "############################################################"
