#!/bin/bash
# ============================================================
# M50：觀察模式改用 qwen2.5vl:3b（放棄 llava:7b）
#
#   根據 M49 trace log 的實測證據：llava:7b 權重載得進 GPU，
#   但真正跑推理時 compute buffer 配置失敗（VRAM 不夠），不是
#   程式邏輯問題，換小模型才是對的路。
#
#   查證結果（來源見對話紀錄）：
#     - qwen2.5vl:3b（Qwen 官方小型多模態模型）：weights 約 3.2GB，
#       GitHub issue #13247 有人在 Jetson Orin 系列（JetPack 6.2.1）
#       實測「GPU 完全 offload、只吃約 1.6GB 顯存」，留給運算緩衝區
#       的餘裕遠比 llava:7b 大很多。
#     - 中文/繁體中文支援是 Qwen 系列強項，比 moondream（純英文訓練，
#       中文 OCR 未經證實）更適合這台車的使用情境。
#     - 注意：qwen3-vl 系列在 Jetson 上有已知的 ARM64 bug（cudaMalloc
#       failed），千萬不要抓成 qwen3-vl，一定是 qwen2.5vl:3b。
#
#   不改 modes.py 原始碼——直接用管理頁已經做好的「模型即時覆寫」
#   功能（/api/mode/config），把 observe 模式的 vlm_model 指向
#   qwen2.5vl:3b。這是這個功能第一次被真正用到。
#
#   驗證方式：不只看模型有沒有「常駐」，而是真的抓一張攝影機畫面、
#   餵給模型跑一次「請用繁體中文描述畫面」的真實推理請求——這才是
#   llava 上次失敗的那一步（load 沒問題，inference 才炸），只看
#   /api/ps 不夠，這次要看到真的有描述文字回來才算過。
# 全程只印原始輸出。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

echo "== [1/7] 取帳密（不印出來，只用來 curl）=="
set -a
source acoustic_app/.env
set +a
AUTH="-u ${ACOUSTIC_USER}:${ACOUSTIC_PASS}"

echo "== [2/7] 從 ollama 拉 qwen2.5vl:3b（約 3.2GB，可能要幾分鐘，請耐心等）=="
curl -sS http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5vl:3b","stream":false}' --max-time 900
echo ""

echo "== [3/7] 確認真的裝進去了（原始 /api/tags）=="
curl -sS http://127.0.0.1:11434/api/tags | grep -o '"name":"qwen2.5vl:3b"' && echo "qwen2.5vl:3b 確認在清單裡" || echo "❌ 沒看到 qwen2.5vl:3b，停下來看上面的 pull 輸出"

echo "== [4/7] 把 observe 模式的 vlm_model 指向 qwen2.5vl:3b（用管理頁的即時覆寫功能）=="
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode/config -H "Content-Type: application/json" -d '{"vlm_model":"qwen2.5vl:3b"}'
echo ""
echo "--- 確認設定生效 ---"
curl -sS $AUTH http://127.0.0.1:8011/api/mode/config
echo ""

echo "== [5/7] 切到 observe，確認起點先清空、再切換，全程看原始 GPU 狀態 =="
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo " ← 先切 manage 清空"
sleep 8
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"observe"}'
echo " ← 切到 observe"

for i in 1 2 3 4; do
  sleep 5
  echo "第 ${i} 次（切換後約 $((i*5)) 秒）："
  curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu
  echo ""
done

echo "== [6/7] 關鍵測試：真的抓一張攝影機畫面，跑一次繁體中文描述推理 =="
python3 <<'PYEOF'
import base64, json, urllib.request, sys

try:
    with urllib.request.urlopen("http://127.0.0.1:8001/frame.jpg", timeout=10) as r:
        img = r.read()
except Exception as e:
    print("❌ 抓攝影機畫面失敗：", type(e).__name__, e)
    sys.exit(1)

b64 = base64.b64encode(img).decode()
print("已抓到畫面，大小：", len(img), "bytes")

body = json.dumps({
    "model": "qwen2.5vl:3b",
    "prompt": "請用繁體中文，簡短描述這張畫面裡有什麼。",
    "images": [b64],
    "stream": False,
    "keep_alive": -1,
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=body,
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = r.read().decode()
except Exception as e:
    print("❌ 推理請求失敗：", type(e).__name__, e)
    sys.exit(1)

print("--- 原始推理回應 ---")
print(resp)
PYEOF

echo ""
echo "--- 推理後再查一次 GPU 狀態（確認沒有像 llava 那樣被炸掉清空）---"
curl -sS $AUTH http://127.0.0.1:8011/api/mode/gpu
echo ""

echo "--- 收工前切回 manage，釋放 GPU ---"
curl -sS $AUTH -X POST http://127.0.0.1:8011/api/mode -H "Content-Type: application/json" -d '{"mode":"manage"}'
echo ""

unset ACOUSTIC_USER ACOUSTIC_PASS

echo "== [7/7] 沒有動任何原始碼，不需要 commit。若上面測試全過，回報我，我來更新設計文件定案。 =="

echo ""
echo "############################################################"
echo "M50 完成。請把 [5/7] 的 4 次輪詢、[6/7] 的『原始推理回應』整段，"
echo "以及最後那次『推理後再查一次 GPU 狀態』的結果，全部貼給我——"
echo "我要親眼看到有繁體中文描述文字回來、而且推理後模型還好好地在"
echo "GPU 上（不是像 llava 那樣被炸掉清空），才算真的定案。"
echo "############################################################"
