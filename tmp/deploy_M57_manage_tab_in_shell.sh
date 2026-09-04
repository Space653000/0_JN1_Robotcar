#!/bin/bash
# ============================================================
# M57：把「管理（開發）駕駛艙」納進首頁 shell 的頁籤列
#
#   Stephen 問「要換網頁嗎」——不用。你本來開的
#   https://robotcar.space653000.workers.dev/ 和 trycloudflare 那個，
#   進去看到的就是 acoustic_app 的 shell.html（8011 的 /），
#   四個頁籤：系統儀表板／聲學即時／視覺即時／助手即時。
#   問題是我從 M46 做的管理駕駛艙一直是獨立頁，要自己打 /manage
#   才進得去，沒有被放進那列頁籤——所以從你平常的入口看不到它。
#   這是我的疏漏，這一步補上。
#
#   做法（只動 shell.html 一個檔案）：
#   1. 頁籤列加第 5 個「管理（開發）」，並在旁邊顯示目前運轉模式
#      （不用進頁籤就看得到現在是哪個模式，點一下直接開管理頁籤）
#   2. 管理頁做成「第一次點才載入」——它每 8 秒會打一次 /api/health
#      （那支會去戳 6 個服務），常駐掛著等於永遠多一組背景輪詢，沒必要
#   3. sel() 改成迴圈版：1~4 的行為跟原本完全一樣，只是多支援第 5 個
#   4. 順手解決一個 iframe 的老問題：各頁的模式標籤指向 /manage、
#      管理頁的四個快速連結指向 /dashboard 等，在 iframe 裡點下去
#      只會把那個 iframe 換掉，看起來像頁面錯亂。因為同源，改由 shell
#      這一端統一把這類連結接成「切頁籤」，四個子頁面一個字都不用動。
#
#   ★ 這一版我不是只做語法檢查——我在本地用 Chromium 真的把改完的
#     shell.html 跑起來、實際點過頁籤，驗證了：
#       ① 頁籤列變成 5 個且有「管理（開發）」
#       ② 上方模式標籤正確顯示（後端回 patrol → 顯示「🏃 巡航」）
#       ③ 沒點之前 /manage 完全沒有被請求（延遲載入有效）
#       ④ 點下去才載入，且只有 f5 顯示
#       ⑤ 在管理頁裡點「視覺即時」→ 切到第3個頁籤，不是把 iframe 換掉
#       ⑥ 點回原本的頁籤照常、上方系統資源條照常
#     截圖也一起給 Stephen 看過了。
#
#   另外這支會先印出 cloudflared 到底轉發到哪個 port，確認你那兩個
#   網址連的是 8011（我做的東西）而不是 8080（舊的 webui 介面）。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

echo "== [0/6] 先確認：你那兩個網址到底連到哪個服務 =="
echo "--- cloudflared 完整指令（看 --url 指向哪個 port）---"
pgrep -a cloudflared 2>/dev/null || echo "（沒找到 cloudflared 程序）"
echo "--- 8011 = acoustic_app（我這十幾步做的東西）---"
curl -sS -o /dev/null -w "  HTTP %{http_code}\n" http://127.0.0.1:8011/ || true
echo "--- 8080 = 舊的 webui 介面（不同的東西）---"
curl -sS -o /dev/null -w "  HTTP %{http_code}\n" http://127.0.0.1:8080/ || true

TS=$(date +%Y%m%d%H%M%S)
FILE="acoustic_app/static/shell.html"

echo ""
echo "== [1/6] 備份 $FILE =="
cp -v "$FILE" "$FILE.bak.$TS"

echo ""
echo "== [2/6] 套用改動（三個錨點都要剛好出現一次）=="
cat > /tmp/m57_patch_$$.py <<'M57PATCHEOF'
#!/usr/bin/env python3
# M57：把「管理（開發）駕駛艙」納進 shell.html 的頁籤列。
# 只動 shell.html 一個檔案。部署腳本與本地驗證共用同一份。
import sys, os

PATH = "acoustic_app/static/shell.html"

# ---------- 1) 頁籤列：加第 5 個頁籤 + 目前模式標籤 ----------
OLD_TAB = '<button id="t4" aria-selected="false" onclick="sel(4)">助手即時</button>'
NEW_TAB = (
    '<button id="t4" aria-selected="false" onclick="sel(4)">助手即時</button>'
    '<button id="t5" aria-selected="false" onclick="sel(5)">管理（開發）</button>'
    '<a href="#" id="jn1AttnMode" onclick="sel(5);return false;" '
    'style="margin-left:10px;font:600 12px system-ui;padding:5px 11px;border-radius:20px;'
    'background:#0c1517;border:1px solid #1e2d31;color:#8aa1a6;text-decoration:none;cursor:pointer" '
    'title="目前運轉模式，點一下開啟管理（開發）駕駛艙">讀取中…</a>'
)

# ---------- 2) iframe：加第 5 個（延遲載入，避免常駐多一組健康檢查輪詢）----------
OLD_FRAME = '<iframe id="f4" src="/assistant"></iframe>'
NEW_FRAME = (
    '<iframe id="f4" src="/assistant"></iframe>'
    '<iframe id="f5" data-src="/manage"></iframe>'
)

# ---------- 3) sel()：改成迴圈版（1~4 行為完全相同），並處理延遲載入與跨頁籤連結 ----------
OLD_SEL = """function sel(n){t1.setAttribute('aria-selected',n===1);t2.setAttribute('aria-selected',n===2);t3.setAttribute('aria-selected',n===3);t4.setAttribute('aria-selected',n===4);
f1.className=n===1?'on':'';f2.className=n===2?'on':'';f3.className=n===3?'on':'';f4.className=n===4?'on':'';}"""

NEW_SEL = """/* M57：改成迴圈版，1~4 的行為跟原本完全一樣，只是多支援第 5 個頁籤。 */
function sel(n){
  for(var i=1;i<=5;i++){
    var t=document.getElementById('t'+i), f=document.getElementById('f'+i);
    if(t)t.setAttribute('aria-selected',i===n);
    if(f)f.className=(i===n?'on':'');
  }
  /* 管理頁第一次被點開才真的載入：它每 8 秒會打一次 /api/health（會去戳 6 個
     服務），常駐掛著等於永遠多一組背景輪詢，沒必要。 */
  var f5=document.getElementById('f5');
  if(n===5&&f5&&!f5.getAttribute('src')&&f5.getAttribute('data-src')){
    f5.setAttribute('src',f5.getAttribute('data-src'));
  }
}
window.jn1SelTab=sel;

/* M57：四頁裡本來就有的連結（例如各頁的模式標籤指向 /manage、管理頁的
   四個快速連結指向 /dashboard 等），在 iframe 裡點下去只會把那個 iframe
   換掉，看起來像頁面錯亂。這裡由 shell 這一端統一處理：因為同源，
   shell 可以在每個 iframe 載入完成後，把這類連結改成「切頁籤」。
   全部包在 try 裡，萬一哪天不同源或結構變了就自動退回原本行為。 */
var JN1_PATH2TAB={'/dashboard':1,'/acoustic':2,'/vision':3,'/assistant':4,'/manage':5};
function jn1WireFrameLinks(fr){
  try{
    var d=fr.contentDocument;
    if(!d)return;
    var as=d.querySelectorAll('a[href]');
    for(var i=0;i<as.length;i++){
      var a=as[i], n=JN1_PATH2TAB[a.getAttribute('href')];
      if(!n||a.getAttribute('data-jn1-wired'))continue;
      a.setAttribute('data-jn1-wired','1');
      (function(tab){a.addEventListener('click',function(e){e.preventDefault();sel(tab);});})(n);
    }
  }catch(e){}
}
(function(){
  for(var i=1;i<=5;i++){
    (function(fr){ if(fr)fr.addEventListener('load',function(){jn1WireFrameLinks(fr);}); })(document.getElementById('f'+i));
  }
})();

/* M57：shell 最上面也顯示目前模式，不用進頁籤就看得到。 */
var JN1_ATTN_ICON={manage:"\U0001F39B️",chat:"\U0001F5E3️",observe:"\U0001F441️",patrol:"\U0001F3C3",standby:"\U0001F634"};
async function jn1RefreshAttnMode(){
  try{
    const r=await fetch('/api/mode',{cache:'no-store'});const d=await r.json();
    const el=document.getElementById('jn1AttnMode');
    if(el&&d&&d.all&&d.mode&&d.all[d.mode]){el.textContent=(JN1_ATTN_ICON[d.mode]||'\\u25CF')+' '+d.all[d.mode].label;}
  }catch(e){}
}
jn1RefreshAttnMode();setInterval(jn1RefreshAttnMode,15000);"""

EDITS = [(OLD_TAB, NEW_TAB), (OLD_FRAME, NEW_FRAME), (OLD_SEL, NEW_SEL)]


def apply_all(root):
    full = os.path.join(root, PATH)
    with open(full, encoding="utf-8") as f:
        src = f.read()
    orig_len = len(src)
    for old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print(f"[FAIL] {PATH}: 錨點出現 {n} 次（應為1）-> {old[:50]!r}")
            print("不動檔案，回報這行給我")
            sys.exit(1)
        src = src.replace(old, new, 1)
    print(f"[檢查OK] {PATH}: {orig_len} -> {len(src)} 字元")
    with open(full, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"[已寫入] {PATH}")


if __name__ == "__main__":
    apply_all(sys.argv[1] if len(sys.argv) > 1 else ".")

M57PATCHEOF
python3 /tmp/m57_patch_$$.py "$REPO"
rm -f /tmp/m57_patch_$$.py

echo ""
echo "== [3/6] JS 語法檢查（有 node 就跑，沒有就跳過，我本地已驗過）=="
if command -v node >/dev/null 2>&1; then
python3 - <<'CHKEOF'
import re, subprocess, os
s=open("acoustic_app/static/shell.html",encoding="utf-8").read()
bad=0
for i,b in enumerate(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',s,re.S)):
    t=f"/tmp/_m57chk_{i}.js"; open(t,"w",encoding="utf-8").write(b)
    r=subprocess.run(["node","--check",t],capture_output=True,text=True)
    print(f"  區塊{i}: {'語法 OK' if r.returncode==0 else '語法錯誤 '+r.stderr[:300]}")
    if r.returncode: bad+=1
    os.remove(t)
print(f"  語法錯誤數：{bad}")
CHKEOF
else
  echo "（沒有 node，跳過）"
fi

echo ""
echo "== [4/6] 重啟 jn1-web，確認首頁與五個頁面都正常 =="
systemctl --user restart jn1-web
sleep 3
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

echo -n "首頁 / HTTP："; curl -sS $AUTH -o /tmp/_shell.html -w "%{http_code}\n" http://127.0.0.1:8011/
echo -n "  [新] 管理頁籤按鈕(t5)："; grep -c 'id="t5"' /tmp/_shell.html || true
echo -n "  [新] 管理 iframe 延遲載入(data-src)："; grep -c 'data-src="/manage"' /tmp/_shell.html || true
echo -n "  [新] 上方模式標籤："; grep -c 'jn1AttnMode' /tmp/_shell.html || true
echo -n "  [新] 跨頁籤連結處理："; grep -c 'jn1WireFrameLinks' /tmp/_shell.html || true
echo -n "  [舊] 四個原本的頁籤(t1~t4)："; grep -o 'id="t[1-4]"' /tmp/_shell.html | wc -l
echo -n "  [舊] 四個原本的 iframe(f1~f4)："; grep -o 'id="f[1-4]"' /tmp/_shell.html | wc -l
echo -n "  [舊] 系統資源條 tele："; grep -c 'id="tele"' /tmp/_shell.html || true
echo -n "  [舊] /api/telemetry 輪詢："; grep -c "api/telemetry" /tmp/_shell.html || true
rm -f /tmp/_shell.html

for P in /dashboard /acoustic /vision /assistant /manage; do
  echo -n "  $P HTTP："; curl -sS $AUTH -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8011$P"
done

echo ""
echo "== [5/6] 目前模式（shell 上方標籤會顯示這個）=="
curl -sS $AUTH http://127.0.0.1:8011/api/mode | head -c 400
echo ""
unset ACOUSTIC_USER ACOUSTIC_PASS

echo ""
echo "== [6/6] git commit + push =="
git add "$FILE"
git status --short
git commit -m "M57: 管理駕駛艙納進首頁 shell 頁籤列（第5個頁籤）

- Stephen 平常從 workers.dev / trycloudflare 進來看到的是 shell.html
  的四個頁籤，但 M46 做的管理駕駛艙一直是要自己打 /manage 的獨立頁，
  沒被放進頁籤列，等於從正常入口看不到。這步補上
- 頁籤列加第5個「管理（開發）」，旁邊顯示目前運轉模式，點一下直接開
- 管理頁做成第一次點才載入：它每8秒打一次 /api/health(戳6個服務)，
  常駐掛著等於永遠多一組背景輪詢
- sel() 改迴圈版，1~4 行為完全不變
- 順手修 iframe 老問題：子頁面裡指向其他頁的連結，改由 shell 端接成
  切頁籤（同源），四個子頁面一個字都沒動
- 驗證方式：本地用 Chromium 真的把 shell 跑起來實際點過頁籤，確認
  5個頁籤/模式標籤/延遲載入/跨頁籤連結/原本頁籤與遙測條全部正常

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
echo "M57 完成。請把 [0/6]（cloudflared 指向哪個 port）跟 [4/6] 的"
echo "驗證輸出貼給我。"
echo ""
echo "然後 Stephen 直接用你原本的網址重新整理一次："
echo "  https://robotcar.space653000.workers.dev/"
echo "應該會看到頁籤列從 4 個變 5 個，多一個「管理（開發）」，"
echo "旁邊還有一個顯示目前模式的小標籤。點進去就能切五模式，"
echo "不用再自己打網址、也不用進終端機。"
echo "############################################################"
