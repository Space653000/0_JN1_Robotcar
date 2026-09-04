#!/bin/bash
# ============================================================
# M58：讓 MODES 的 cloud 旗標真的生效（藍圖步驟 4：巡航/待機不上雲）
#
#   缺口（讀原始碼查到的，不是猜的）：
#   藍圖注意力槽那張表寫著巡航「雲端：關/靜音」、待機「雲端：關」，
#   modes.py 的 MODES 也確實宣告了 cloud:False——但**沒有任何一行程式
#   在讀這個旗標**。brain 的 /ask 只要本地答案弱就照打雲端，不管現在
#   是什麼模式。而且 brain 容器根本看不到目前模式：它沒掛 data/、
#   也沒有任何指向 web app 的設定。
#
#   做法（三個檔案，刻意不複製第二份設定表）：
#   1. modes.py：切模式時把「解析後的旗標」一起寫進 data/mode.json
#      （cloud/vision/vlm/big/label）。MODES 仍是唯一事實來源，這裡
#      只是把它解析後的結果落地給別的行程用。
#      同時改成原子寫入（先寫 .tmp 再 rename）——現在有跨行程讀者了，
#      直接覆寫有機會讓對方讀到寫到一半的檔案。
#   2. docker-compose.yml：brain 唯讀掛載 ./data 到 /appdata。
#      ★ 必須掛「整個目錄」不能單掛 mode.json：rename 會換 inode，
#        單掛檔案的話容器會永遠卡在舊 inode 上，看不到任何更新。
#      （這是很容易踩的坑，特別寫在這裡。）
#   3. brain/server.py：打雲端前先看旗標；被擋下來時在回應裡照實寫明
#      cloud_skipped 跟原因，不要看起來像「問過雲端但雲端沒東西」。
#
#   fail-safe：檔案不見、內容壞掉、或舊格式沒有 cloud 欄位，一律當成
#   「允許上雲」＝維持現有行為，不會因為這個功能出問題就把雲端關掉。
#
#   ★ 本地已實測（不是只看語法）：用改完的 modes.py 真的呼叫 set_mode
#     寫檔，再把改完的 brain/server.py 裡那段閘門程式碼原封不動抽出來
#     執行去讀，五個模式的判定全部符合藍圖，三種 fail-safe 也都正確。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)

echo "== [1/8] 備份三個檔案 =="
cp -v acoustic_app/modes.py "acoustic_app/modes.py.bak.$TS"
cp -v docker-compose.yml "docker-compose.yml.bak.$TS"
cp -v src/brain/server.py "src/brain/server.py.bak.$TS"

echo ""
echo "== [2/8] 套用改動（所有錨點確認完才寫檔）=="
cat > /tmp/m58_patch_$$.py <<'M58PATCHEOF'
#!/usr/bin/env python3
# M58：讓 MODES 宣告的 cloud 旗標真的生效（藍圖步驟 4：巡航/待機不上雲）
# 部署腳本與本地驗證共用同一份。
import sys, os

EDITS = [
# ---------------------------------------------------------------
# 1) modes.py：切模式時把「解析後的旗標」一起寫進 data/mode.json
#    這樣別的行程（docker 裡的 brain）不必自己再複製一份 MODES 表。
#    MODES 仍是唯一事實來源，這裡只是把結果落地。
#    同時改成原子寫入，因為現在有跨行程的讀者了。
# ---------------------------------------------------------------
("acoustic_app/modes.py", [
("""    st = {"mode": mode, "ts": time.time()}
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(st, f)
    except Exception as e:
        return {"ok": False, "error": "write state failed: " + type(e).__name__}""",
"""    # M58：把解析後的旗標一起寫進去，讓別的行程（例如 docker 裡的 brain）
    # 不必自己再複製一份 MODES 表，就能知道現在該不該用雲端、視覺該多快。
    # MODES 仍然是唯一的事實來源，這裡只是把「它解析後的結果」落地。
    st = {"mode": mode, "ts": time.time(),
          "label": m.get("label"),
          "big": m.get("big"),
          "vlm": m.get("vlm", False),
          "cloud": m.get("cloud", True),
          "vision": m.get("vision")}
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        # M58：原子寫入（先寫暫存檔再 rename）。現在有跨行程的讀者了，
        # 直接覆寫有機會讓對方讀到寫到一半的檔案。
        # 註：因為 rename 會換 inode，docker 那邊必須掛「整個 data 目錄」，
        # 單獨掛這個檔案的話容器會永遠卡在舊 inode 上看不到更新。
        _tmp = STATE_FILE + ".tmp"
        with open(_tmp, "w") as f:
            json.dump(st, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(_tmp, STATE_FILE)
    except Exception as e:
        return {"ok": False, "error": "write state failed: " + type(e).__name__}"""),
]),

# ---------------------------------------------------------------
# 2) docker-compose.yml：brain 唯讀掛載 data/，並告訴它檔案在哪
# ---------------------------------------------------------------
("docker-compose.yml", [
("""      - LISTEN_SECONDS=${LISTEN_SECONDS:-5}
    ports:
      - "127.0.0.1:${BRAIN_PORT:-21500}:8000"
    depends_on: [ollama-new, asr, tts, vision]""",
"""      - LISTEN_SECONDS=${LISTEN_SECONDS:-5}
      - JN1_MODE_FILE=/appdata/mode.json          # M58：五模式狀態（唯讀）
    ports:
      - "127.0.0.1:${BRAIN_PORT:-21500}:8000"
    volumes:
      # M58：唯讀掛整個 data 目錄（不是單掛 mode.json）——modes.py 用
      # rename 做原子寫入會換 inode，單掛檔案會讓容器看不到更新。
      - ./data:/appdata:ro
    depends_on: [ollama-new, asr, tts, vision]"""),
]),

# ---------------------------------------------------------------
# 3) brain/server.py：讀旗標，打雲端前先檢查
# ---------------------------------------------------------------
("src/brain/server.py", [
("""import os
import re
import time""",
"""import os
import re
import json
import time"""),

('''CLOUD_GW = os.environ.get("CLOUD_GW_URL", "http://cloud-gw:8000")''',
'''CLOUD_GW = os.environ.get("CLOUD_GW_URL", "http://cloud-gw:8000")

# ---- M58：五模式的「雲端」旗標 ----------------------------------------
# 藍圖裡巡航是「移動中保持警覺、雲端關/靜音」，待機是「打盹省電、雲端關」，
# modes.py 也早就宣告了 cloud:False，但一直沒有任何程式在讀它。
# 這裡刻意不複製一份 MODES 表：modes.py 每次切模式都會把解析後的旗標寫進
# data/mode.json，brain 唯讀掛載後直接讀那個結果，維持單一事實來源。
JN1_MODE_FILE = os.environ.get("JN1_MODE_FILE", "/appdata/mode.json")


def _jn1_mode_state():
    try:
        with open(JN1_MODE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _mode_allows_cloud():
    """讀不到檔案、或檔案裡沒這個欄位時一律回 True（維持現有行為，不會因為
    模式功能出問題就把雲端整個關掉）。只有明確寫著 cloud:false 才擋。"""
    return _jn1_mode_state().get("cloud", True) is not False
# ----------------------------------------------------------------------'''),

('''    if intent == "chat" and _local_answer_weak(res.get("reply", "")):
        _c = _ask_cloud(req.text)
        if _c:
            res["reply"] = _c
            res["source"] = "cloud"''',
'''    if intent == "chat" and _local_answer_weak(res.get("reply", "")):
        if _mode_allows_cloud():
            _c = _ask_cloud(req.text)
            if _c:
                res["reply"] = _c
                res["source"] = "cloud"
        else:
            # M58：巡航/待機不上雲。照實在回應裡講明有跳過、為什麼跳過，
            # 不要讓它看起來像「問過雲端但雲端沒東西」。
            _st = _jn1_mode_state()
            res["cloud_skipped"] = {"reason": "mode_cloud_off",
                                    "mode": _st.get("mode"),
                                    "label": _st.get("label")}'''),
]),
]


def apply_all(root):
    """兩階段：所有檔案的所有錨點全部確認完，才開始寫檔。"""
    staged = []
    for path, edits in EDITS:
        full = os.path.join(root, path)
        with open(full, encoding="utf-8") as f:
            src = f.read()
        orig_len = len(src)
        for old, new in edits:
            n = src.count(old)
            if n != 1:
                print(f"[FAIL] {path}: 錨點出現 {n} 次（應為1）-> {old.strip()[:50]!r}")
                print("所有檔案都不動，回報這行給我")
                sys.exit(1)
            src = src.replace(old, new, 1)
        print(f"[檢查OK] {path}: {orig_len} -> {len(src)} 字元")
        staged.append((full, path, src, orig_len))

    print("--- 所有錨點確認完畢，開始寫檔 ---")
    for full, path, src, orig_len in staged:
        with open(full, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"[已寫入] {path}: {orig_len} -> {len(src)} 字元")


if __name__ == "__main__":
    apply_all(sys.argv[1] if len(sys.argv) > 1 else ".")

M58PATCHEOF
python3 /tmp/m58_patch_$$.py "$REPO"
rm -f /tmp/m58_patch_$$.py

echo ""
echo "== [3/8] 語法/結構檢查 =="
python3 -c "
import ast
for p in ['acoustic_app/modes.py','src/brain/server.py']:
    ast.parse(open(p,encoding='utf-8').read()); print('  ',p,'語法 OK')
" || { echo "語法錯誤！回復：cp acoustic_app/modes.py.bak.$TS acoustic_app/modes.py; cp src/brain/server.py.bak.$TS src/brain/server.py"; exit 1; }
python3 -c "
import yaml
d=yaml.safe_load(open('docker-compose.yml',encoding='utf-8'))
b=d['services']['brain']
print('   brain volumes:', b.get('volumes'))
print('   服務數量:', len(d['services']))
" || { echo "compose 檔壞了！回復：cp docker-compose.yml.bak.$TS docker-compose.yml"; exit 1; }

echo ""
echo "== [4/8] 重啟 jn1-web（modes.py 跑在 host），讓新的寫檔格式生效 =="
systemctl --user restart jn1-web
sleep 3
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"
echo "--- 切一次模式，讓它用新格式重寫 mode.json ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '"'"'{"mode":"manage"}'"'"' >/dev/null
sleep 1
echo "--- data/mode.json 現在的內容（要有 cloud/vision 這些欄位）---"
cat data/mode.json; echo

echo ""
echo "== [5/8] 重建 brain 映像檔（image-build，不是 bind mount）＋帶上新的掛載 =="
docker compose build brain
docker compose up -d brain
sleep 6
echo "--- brain 健康檢查 ---"
curl -sS http://127.0.0.1:${BRAIN_PORT:-21500}/health | head -c 300; echo

echo ""
echo "== [6/8] 關鍵驗證：brain 容器真的看得到 mode.json 嗎 =="
echo "--- 容器裡的 /appdata/mode.json ---"
docker compose exec -T brain cat /appdata/mode.json || echo "（讀不到！掛載沒生效）"
echo ""

echo "== [7/8] 逐一切五個模式，看容器裡的閘門怎麼判定 =="
for M in manage chat observe patrol standby; do
  curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d "{\"mode\":\"$M\"}" >/dev/null
  sleep 2
  echo -n "  $M -> "
  docker compose exec -T brain python3 -c "
from server import _mode_allows_cloud, _jn1_mode_state
st=_jn1_mode_state()
print('mode.json裡 mode=%s cloud=%s  ->  brain判定允許上雲=%s' % (st.get('mode'), st.get('cloud'), _mode_allows_cloud()))
"
done
echo ""
echo "  （藍圖要求：管理/對話/觀察 = True，巡航/待機 = False）"

echo ""
echo "--- 順便看一次巡航模式下真的問一句話，回應長怎樣 ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '"'"'{"mode":"patrol"}'"'"' >/dev/null
sleep 3
curl -sS -X POST http://127.0.0.1:${BRAIN_PORT:-21500}/ask \
  -H "Content-Type: application/json" \
  -d '"'"'{"text":"量子糾纏的貝爾不等式怎麼推導","speak":false}'"'"' --max-time 90 | head -c 700
echo ""
echo "  （如果本地答案被判定為弱，巡航模式下應該會出現 cloud_skipped 欄位，"
echo "    而不是 source:cloud）"

echo "--- 收工切回管理模式 ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '"'"'{"mode":"manage"}'"'"'
echo ""
unset ACOUSTIC_USER ACOUSTIC_PASS

echo ""
echo "== [8/8] git commit + push =="
git add acoustic_app/modes.py docker-compose.yml src/brain/server.py
git status --short
git commit -m "M58: 讓 MODES 的 cloud 旗標真的生效（巡航/待機不上雲）

- 缺口：藍圖與 MODES 都宣告巡航/待機 cloud:False，但沒有任何程式在讀，
  brain /ask 只要本地答案弱就照打雲端；而且 brain 容器沒掛 data/、
  根本看不到目前是什麼模式
- modes.py：set_mode 把解析後的旗標(cloud/vision/vlm/big/label)一起寫進
  data/mode.json，並改成原子寫入(.tmp + rename)，因為現在有跨行程讀者
- docker-compose：brain 唯讀掛 ./data 到 /appdata。必須掛整個目錄，
  單掛 mode.json 會因為 rename 換 inode 而永遠看不到更新
- brain：打雲端前檢查旗標；被擋時回應裡照實寫 cloud_skipped 跟原因
- 刻意不複製第二份設定表——MODES 仍是唯一事實來源(記取 M51/M56 教訓)
- fail-safe：檔案不見/壞掉/舊格式沒該欄位，一律允許上雲＝維持現有行為
- 本地已用改完的 modes.py 實際寫檔 + 改完的 brain 閘門程式碼實際讀取，
  驗證五個模式判定全部符合藍圖、三種 fail-safe 都正確

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
echo "M58 完成。最關鍵的是 [6/8] 和 [7/8]："
echo "  [6/8] brain 容器到底讀不讀得到 /appdata/mode.json"
echo "  [7/8] 五個模式的判定是不是 管理/對話/觀察=True、巡航/待機=False"
echo "這兩段整段貼給我。如果 [6/8] 讀不到，就是掛載沒生效，先別管其他。"
echo "############################################################"
