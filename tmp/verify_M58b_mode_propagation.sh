#!/bin/bash
# ============================================================
# M58b：重驗 M58，修掉我自己驗證腳本的兩個缺陷。不改任何檔案（唯讀）。
#
#   終端機抓到的兩件事都成立，這裡逐一處理：
#
#   缺陷一：shell 引號寫錯。我在三處用了 '"'"' 這個「單引號內嵌單引號」
#   的慣用寫法，但那個位置不在單引號裡，結果 curl 送出的 body 是
#   "'{mode:manage}'"（一個 JSON 字串，不是物件）→ FastAPI 直接 422。
#   其中 [4/8] 那條後面接 >/dev/null，等於靜靜地失敗沒人看得到，
#   代表「切一次模式讓它用新格式重寫 mode.json」根本沒執行到。
#   這支已經在本地對著 stub server 實測過，確認送出的是合法物件。
#
#   缺陷二（比較嚴重）：我的檢查方法本身會製造假通過。
#   原本只比對 cloud 這個「衍生值」，從來沒比對「讀回來的 mode 是不是
#   我剛設的那個」。少了身分比對，過期的讀取就能偽裝成正確——patrol
#   和 standby 的 cloud 剛好都是 False，所以讀到舊檔案也「看起來對」。
#   這支的每一項都先比對 mode 身分，不符就直接標記失敗。
#
#   而且刻意選 cloud 會「翻面」的轉換來測（False→True、True→False），
#   這樣一旦讀到過期內容，判定結果一定會錯、藏不住。
#
#   另外不再盲等 sleep：直接在容器內輪詢量「切完模式後多久才看得到」，
#   順便回答一個真正的產品問題——切到巡航後馬上問問題，會不會還來得及
#   跑去打雲端。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

echo "== [1/4] 先確認 mode.json 目前到底有沒有新欄位 =="
echo "（因為 M58 的 [4/8] 那次寫入其實沒執行到，這裡重新確認）"
echo "--- host 端 data/mode.json ---"
cat data/mode.json; echo
echo "--- 容器裡 /appdata/mode.json ---"
docker compose exec -T brain cat /appdata/mode.json; echo

echo ""
echo "== [2/4] 先驗證這支自己的 curl 是不是真的送出合法 JSON（不再重蹈覆轍）=="
echo -n "  送出 {\"mode\":\"manage\"} 的 HTTP 狀態碼："
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"manage"}' -o /tmp/_m58b_resp.txt -w "%{http_code}\n"
echo "  回應內容：$(cat /tmp/_m58b_resp.txt)"
echo "  （要是 200 且回應是模式狀態；如果是 422 就代表引號又寫錯了，停下來別往下看）"
rm -f /tmp/_m58b_resp.txt

echo ""
echo "== [3/4] 用 cloud 會翻面的轉換來測，每一項都先比對 mode 身分 =="
echo "   （順序刻意讓 cloud 一直 True/False 交替，讀到過期內容一定會被抓到）"
echo ""

check_mode () {
  local M="$1" WANT_CLOUD="$2"
  # 送出切換（正確引號，變數用雙引號＋跳脫）
  curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode \
    -H "Content-Type: application/json" \
    -d "{\"mode\":\"$M\"}" -o /dev/null -w "" || true

  # 進容器輪詢：不盲等，量它多久才看得到，並且一定要比對 mode 身分
  docker compose exec -T brain python3 -c "
import time, sys
sys.path.insert(0,'/app')
from server import _jn1_mode_state, _mode_allows_cloud
want_mode='$M'
want_cloud=('$WANT_CLOUD'=='True')
t0=time.time()
first=_jn1_mode_state()
seen=None; elapsed=None
for i in range(60):                      # 最多等 6 秒
    st=_jn1_mode_state()
    if st.get('mode')==want_mode:
        seen=st; elapsed=time.time()-t0; break
    time.sleep(0.1)
if seen is None:
    print('  %-8s ❌ 等了6秒，容器裡的 mode 還是 %r，不是 %r'
          % (want_mode, first.get('mode'), want_mode))
    sys.exit(1)
allow=_mode_allows_cloud()
ok_id   = (seen.get('mode')==want_mode)
ok_cloud= (allow==want_cloud)
mark='✅' if (ok_id and ok_cloud) else '❌'
print('  %-8s %s 身分比對: mode=%s(要 %s)  cloud=%s -> 允許上雲=%s(要 %s)  容器看到的延遲: %.0f ms  第一次讀就正確: %s'
      % (want_mode, mark, seen.get('mode'), want_mode, seen.get('cloud'),
         allow, want_cloud, elapsed*1000, first.get('mode')==want_mode))
if not (ok_id and ok_cloud):
    sys.exit(1)
"
}

FAIL=0
# 刻意讓 cloud 交替翻面：False -> True -> False -> True -> False
check_mode patrol  False || FAIL=1
check_mode chat    True  || FAIL=1
check_mode standby False || FAIL=1
check_mode observe True  || FAIL=1
check_mode patrol  False || FAIL=1
check_mode manage  True  || FAIL=1

echo ""
if [ "$FAIL" = "0" ]; then
  echo "  === 六次轉換全部通過：每一次的 mode 身分都對得上，cloud 判定也都符合藍圖 ==="
else
  echo "  === 有項目失敗，上面標 ❌ 的那幾行就是，整段貼回來給我 ==="
fi

echo ""
echo "== [4/4] 收工確認目前狀態 =="
curl -sS $AUTH http://127.0.0.1:8011/api/mode | head -c 200; echo
unset ACOUSTIC_USER ACOUSTIC_PASS

echo ""
echo "############################################################"
echo "這支不改任何檔案，純重驗。請把 [1/4]～[3/4] 整段貼給我。"
echo "我最想看的是 [3/4] 每一行的「容器看到的延遲 X ms」和"
echo "「第一次讀就正確: True/False」——這決定要不要再補一層保護："
echo "如果延遲接近 0、第一次讀就正確，代表切到巡航後馬上問問題也不會"
echo "漏打雲端，M58 就真的完整了；如果有明顯延遲，那是真的要處理的問題。"
echo "############################################################"
