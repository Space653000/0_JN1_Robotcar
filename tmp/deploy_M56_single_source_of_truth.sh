#!/bin/bash
# ============================================================
# M56：把「模式→視覺頻率」的唯一事實來源收回 modes.py
#      ＋ 印出網頁的實際存取網址（Stephen 問的）
#
#   為什麼要改（老實說，這是我 M55 自己埋的）：
#   modes.py 的 MODES 本來就宣告了每個模式的 vision 旗標
#   （manage/observe=normal、chat=low、patrol=high、standby=off），
#   但我在 M55 的 JS 裡「又寫了一份」用模式名稱當 key 的頻率表。
#   兩份設定上線第一天就對不上了：modes.py 說 observe 是 normal，
#   我的 JS 卻給它 detect=400（比 normal 的 700 快）。
#   這跟 M51 抓到的「兩套 VLM 設定各自為政」是同一種錯，趁還沒往上
#   疊東西先改掉，之後 modes.py 改旗標，四頁會自動跟著改。
#
#   觀察模式因此回到 normal(700ms)——它的「看仔細」本來就不是靠把
#   YOLO 拉快，而是靠 VLM 整句描述＋自動唸出來（M55 已經做了）。
#
#   fail-safe 不變：旗標讀不到或是沒看過的值，四頁完全退回原本的
#   90/700/120。我已經在本地用「真的 modes.py ＋ 改完檔案裡真的 JS」
#   跑過整張對照表驗證過了。
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
for F in "$DASH" "$ACOU" "$VIS" "$ASST"; do cp -v "$F" "$F.bak.$TS"; done

echo ""
echo "== [2/6] 套用改動（兩階段：四個錨點全部確認完才寫檔）=="
cat > /tmp/m56_patch_$$.py <<'M56PATCHEOF'
#!/usr/bin/env python3
# M56：把「模式→視覺頻率」的唯一事實來源收回 modes.py。
# 部署腳本和本地預先驗證共用同一份，避免驗的跟部署的不一樣。
import sys, os

# M55 種下的那段（四頁各一份，一字不差）
OLD = '''window.JN1_MODE='';
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
};'''

NEW = '''window.JN1_MODE='';
/* M56：頻率表改用 modes.py 宣告的 vision 旗標當 key（normal/low/high/off），
   不再自己維護一份「模式名稱→頻率」的對照表。
   modes.py 是唯一的事實來源，那邊改了這裡自動跟著改。
   （M55 我寫成用模式名稱當 key，等於又生出第二份設定，而且上線當天
     就跟 modes.py 對不上：modes.py 說 observe 是 normal，JS 卻給它
     400ms。跟 M51 抓到的「兩套 VLM 設定各自為政」是同一種錯，改掉。）
   觀察模式的「看仔細」不是靠把 YOLO 拉快，而是靠 VLM 整句描述＋
   自動唸出來（M55 已經做了），所以它回到 normal 才是對的。 */
window.JN1_VISION='';
window.JN1_RATE={
  normal:{frame:90,  detect:700,  thumb:120 },
  low   :{frame:300, detect:1500, thumb:120 },
  high  :{frame:90,  detect:300,  thumb:600 },
  off   :{frame:3000,detect:6000, thumb:3000}
};
window.jn1Rate=function(key,fallback){
  var r=window.JN1_RATE[window.JN1_VISION];
  return (r&&r[key]!=null)?r[key]:fallback;
};'''

# 同時讓刷新函式把 vision 旗標存下來
OLD2 = '''    if(d&&d.mode&&d.mode!==window.JN1_MODE){
      var prev=window.JN1_MODE;window.JN1_MODE=d.mode;
      if(typeof window.jn1OnModeChange==='function'){try{window.jn1OnModeChange(d.mode,prev);}catch(e){}}
    }'''

NEW2 = '''    if(d&&d.mode&&d.all&&d.all[d.mode]){window.JN1_VISION=d.all[d.mode].vision||'';}
    if(d&&d.mode&&d.mode!==window.JN1_MODE){
      var prev=window.JN1_MODE;window.JN1_MODE=d.mode;
      if(typeof window.jn1OnModeChange==='function'){try{window.jn1OnModeChange(d.mode,prev);}catch(e){}}
    }'''

FILES = [
    "acoustic_app/static/vision.html",
    "acoustic_app/static/index.html",
    "acoustic_app/static/assistant.html",
    "jn1_dashboard.html",
]


def apply_all(root):
    """兩階段：四個檔案的錨點全部確認完才開始寫檔。"""
    staged = []
    for path in FILES:
        full = os.path.join(root, path)
        with open(full, encoding="utf-8") as f:
            src = f.read()
        orig_len = len(src)
        for old, new in ((OLD, NEW), (OLD2, NEW2)):
            n = src.count(old)
            if n != 1:
                print(f"[FAIL] {path}: 錨點出現 {n} 次（應為1）-> {old[:40]!r}")
                print("四個檔案全部不動，回報這行給我")
                sys.exit(1)
            src = src.replace(old, new, 1)
        print(f"[檢查OK] {path}: {orig_len} -> {len(src)} 字元")
        staged.append((full, path, src, orig_len))

    print("--- 四個檔案錨點全部確認完畢，開始寫檔 ---")
    for full, path, src, orig_len in staged:
        with open(full, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"[已寫入] {path}: {orig_len} -> {len(src)} 字元")


if __name__ == "__main__":
    apply_all(sys.argv[1] if len(sys.argv) > 1 else ".")

M56PATCHEOF
python3 /tmp/m56_patch_$$.py "$REPO"
rm -f /tmp/m56_patch_$$.py

echo ""
echo "== [3/6] 驗證：modes.py 的旗標真的在驅動頻率（用真的 MODES + 改完檔案裡真的 JS）=="
python3 - <<'MODESEOF'
import json, importlib.util, sys, types, re, subprocess, os
sys.modules['httpx']=types.ModuleType('httpx')
spec=importlib.util.spec_from_file_location("m","acoustic_app/modes.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("modes.py 目前宣告的 vision 旗標：")
for k,v in m.MODES.items():
    print(f"   {k:8s} {v.get('label',''):10s} vision={v.get('vision')}")
open("/tmp/_m56_modes.json","w",encoding="utf-8").write(json.dumps(m.MODES,ensure_ascii=False))
MODESEOF

if command -v node >/dev/null 2>&1; then
cat > /tmp/_m56chk_$$.js <<'JSEOF'
const MODES=require('/tmp/_m56_modes.json');
global.window={};
const fs=require('fs');
const html=fs.readFileSync(process.env.REPO+'/acoustic_app/static/vision.html','utf8');
const mm=html.match(/window\.JN1_MODE='';[\s\S]*?window\.jn1Rate=function[\s\S]*?\};/);
if(!mm){console.log('抽不到 JS 區塊');process.exit(1);}
eval(mm[0]);
console.log('');
console.log('模式'.padEnd(10),'旗標'.padEnd(10),'frame'.padStart(6),'detect'.padStart(7),'thumb'.padStart(6));
for(const k of Object.keys(MODES)){
  window.JN1_VISION=MODES[k].vision||'';
  console.log(String(MODES[k].label).padEnd(10),String(MODES[k].vision||'?').padEnd(12),
    String(window.jn1Rate('frame',90)).padStart(6),
    String(window.jn1Rate('detect',700)).padStart(7),
    String(window.jn1Rate('thumb',120)).padStart(6));
}
console.log('\n--- fail-safe：旗標空的 / 沒看過的值，要退回原本的 90/700/120 ---');
for(const v of ['','bogus']){window.JN1_VISION=v;
  console.log(String(v||'(空)').padEnd(23),
    String(window.jn1Rate('frame',90)).padStart(6),
    String(window.jn1Rate('detect',700)).padStart(7),
    String(window.jn1Rate('thumb',120)).padStart(6));}
JSEOF
REPO="$REPO" node /tmp/_m56chk_$$.js
rm -f /tmp/_m56chk_$$.js
else
  echo "（這台沒有 node，跳過這項；我本地已用同樣方式驗過）"
fi

echo ""
echo "== [4/6] 重啟 jn1-web，確認四頁還活著、新舊功能都在 =="
systemctl --user restart jn1-web
sleep 3
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"
get_page () { curl -sS $AUTH "http://127.0.0.1:8011$1"; }

for P in /dashboard /acoustic /vision /assistant; do
  echo "--- $P ---"
  echo -n "  HTTP："; curl -sS $AUTH -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8011$P"
  echo -n "  [新] 用 vision 旗標當 key(JN1_VISION)："; get_page $P | grep -c "window.JN1_VISION" || true
  echo -n "  [新] 舊的模式名稱頻率表已經不在(應為0)："; get_page $P | grep -c "manage :{frame" || true
  echo -n "  [舊] 模式標籤 jn1AttnMode："; get_page $P | grep -c "jn1AttnMode" || true
done

echo "--- 各頁專屬舊功能複檢 ---"
echo -n "vision  btnSpeak/describe/drawBoxes/預警："
get_page /vision | grep -c "btnSpeak\|function describe\|function drawBoxes\|alertPerson" || true
echo -n "acoustic  ws即時/modeBadge/校準/示範模式："
get_page /acoustic | grep -c "ws/live\|id=\"modeBadge\"\|api/calibrate_front\|function startDemo" || true
echo -n "assistant  quick/ask/speak勾選/health："
get_page /assistant | grep -c "id=\"quick\"\|/api/assistant/ask\|id=\"speak\"\|function health" || true
echo -n "dashboard  themeToggle/唸系統狀態："
get_page /dashboard | grep -c "themeToggle\|jn1SpeakStatus" || true

echo ""
echo "== [5/6] Stephen 問的：網頁到底在哪看 =="
echo "--- 這台 Jetson 的區網 IP ---"
hostname -I 2>/dev/null || ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '^127\.'
echo "--- jn1-web 服務狀態 ---"
systemctl --user is-active jn1-web
echo "--- 目前有沒有在跑 cloudflared 隧道（有的話遠端也能連）---"
pgrep -a cloudflared 2>/dev/null || echo "（目前沒有跑 cloudflared 隧道，只能區網連）"
JETIP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "在同一個網路的電腦/手機，用瀏覽器開："
echo "   系統儀表板  http://${JETIP}:8011/dashboard"
echo "   聲學即時    http://${JETIP}:8011/acoustic"
echo "   視覺即時    http://${JETIP}:8011/vision      ← 要看的『更新 X/s』在這頁"
echo "   助手即時    http://${JETIP}:8011/assistant"
echo "   管理駕駛艙  http://${JETIP}:8011/manage      ← 在這裡切模式"
echo "（會跳帳號密碼，就是 acoustic_app/.env 裡的那組）"
unset ACOUSTIC_USER ACOUSTIC_PASS

echo ""
echo "== [6/6] git commit + push =="
git add "$DASH" "$ACOU" "$VIS" "$ASST"
git status --short
git commit -m "M56: 視覺頻率改由 modes.py 的 vision 旗標驅動（收回單一事實來源）

- M55 我在四頁 JS 裡另外寫了一份「模式名稱→頻率」對照表，等於跟
  modes.py 的 vision 旗標(normal/low/high/off)並存成兩份設定，
  而且上線當天就對不上：modes.py 說 observe=normal，JS 卻給 400ms。
  跟 M51 抓到的「兩套 VLM 設定各自為政」同一種錯，這次改掉
- 頻率表改用 vision 旗標當 key，modes.py 成為唯一事實來源，
  之後那邊改旗標四頁自動跟著改，不必再動 HTML
- 觀察模式因此回到 normal(700ms)：它的「看仔細」是靠 VLM 整句描述
  ＋自動唸出來(M55已做)，不是靠把 YOLO 拉快
- fail-safe 不變：旗標讀不到或沒看過的值，四頁完全退回原本
  90/700/120。已用真的 modes.py ＋ 改完檔案裡真的 JS 跑過整張對照表

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
echo "M56 完成。請把 [3/6] 的對照表、[4/6] 的驗證、還有 [5/6] 印出來"
echo "的網址整段貼給我。[5/6] 那幾個網址就是 Stephen 要的答案。"
echo "############################################################"
