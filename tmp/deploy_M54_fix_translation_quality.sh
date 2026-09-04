#!/bin/bash
# ============================================================
# M54：修 _translate_vlm_to_zh() 翻譯偶發不完整的問題
#      （同一段英文，M51 測試翻成「空調風管」，M53 測試卻留下
#        「氣 ducts」這種中英夾雜——同一段程式碼、結果不一致）
#
#   根因（讀 src/brain/server.py 310~332 行原始碼確認）：
#   1. 提示詞太鬆——只說「翻譯成繁體中文」，沒有明講複合詞/專有
#      名詞也要整個翻，qwen2.5:3b 這顆 3B 小模型偶爾會挑字翻一半。
#   2. 沒有指定 temperature，用 ollama 預設值（較高、較隨機），
#      同一句話每次翻譯結果本來就有機會不一樣。
#   3. 沒有任何「翻完檢查」機制——生成後直接回傳，即使結果裡還留
#      著英文字母也不會被抓到重翻。
#
#   修法（只動這一個函式，其他都不碰）：
#   - 提示詞明講「複合詞/專有名詞也要翻」+ 舉例（air ducts→空調風管）
#   - options.temperature 設 0.2，降低同一輸入每次結果不一致的機率
#   - 翻完用 regex 偵測還有沒有殘留的英文字母（連續2個以上），
#     若有，就用更嚴格的提示詞重翻一次（比照既有「timeout 重試」
#     的 for-loop 架構，同一種「偵測問題→自動重試一次」的寫法，
#     跟這個檔案裡本來就有的 _verify_no_hallucination 那套防幻覺
#     檢查是同一種精神）
#
# 全程只印原始輸出，不加工、不摘要判斷。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO"

TS=$(date +%Y%m%d%H%M%S)
FILE="src/brain/server.py"

echo "== [1/7] 備份 $FILE =="
cp -v "$FILE" "$FILE.bak.$TS"

echo "== [2/7] 錨點檢查（整段舊函式要剛好出現一次才動手）=="
python3 <<'PYCHECK'
import sys
path = "src/brain/server.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

OLD = '''def _translate_vlm_to_zh(english_desc: str) -> str:
    """Translate English VLM description to Traditional Chinese via qwen2.5:3b.
    Uses explicit prompt to ensure Taiwan Traditional Chinese output.
    M3-5b：使用 lock 序列化。"""
    try:
        prompt = f"翻譯成繁體中文（台灣用語），一句自然的話，不要清單。英文：{english_desc}"
        with _llm_lock:
            for attempt in range(2):
                try:
                    r = requests.post(f"{OLLAMA}/api/chat",
                                      json={"model": LLM, "stream": False,
                                            "messages": [{"role": "user", "content": prompt}]},
                                      timeout=30)
                    r.raise_for_status()
                    zh_desc = r.json()["message"]["content"].strip()
                    return to_traditional(zh_desc)
                except requests.Timeout:
                    if attempt == 0:
                        time.sleep(0.5)
                    else:
                        raise
    except Exception as e:
        return f"[翻譯失敗: {str(e)[:30]}]"'''

n = src.count(OLD)
print(f"舊函式整段出現次數：{n}")
if n != 1:
    print("不是剛好 1 次，停止，不動任何檔案，回報這個結果給我")
    sys.exit(1)
print("錨點確認 OK，可以替換")
PYCHECK

echo "== [3/7] 替換函式內容 =="
python3 <<'PYEOF'
path = "src/brain/server.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

OLD = '''def _translate_vlm_to_zh(english_desc: str) -> str:
    """Translate English VLM description to Traditional Chinese via qwen2.5:3b.
    Uses explicit prompt to ensure Taiwan Traditional Chinese output.
    M3-5b：使用 lock 序列化。"""
    try:
        prompt = f"翻譯成繁體中文（台灣用語），一句自然的話，不要清單。英文：{english_desc}"
        with _llm_lock:
            for attempt in range(2):
                try:
                    r = requests.post(f"{OLLAMA}/api/chat",
                                      json={"model": LLM, "stream": False,
                                            "messages": [{"role": "user", "content": prompt}]},
                                      timeout=30)
                    r.raise_for_status()
                    zh_desc = r.json()["message"]["content"].strip()
                    return to_traditional(zh_desc)
                except requests.Timeout:
                    if attempt == 0:
                        time.sleep(0.5)
                    else:
                        raise
    except Exception as e:
        return f"[翻譯失敗: {str(e)[:30]}]"'''

NEW = '''def _translate_vlm_to_zh(english_desc: str) -> str:
    """Translate English VLM description to Traditional Chinese via qwen2.5:3b.
    Uses explicit prompt to ensure Taiwan Traditional Chinese output.
    M3-5b：使用 lock 序列化。
    M54：提示詞明講複合詞/專有名詞也要翻＋temperature降低＋翻完偵測殘留
         英文字母，若有就用更嚴格提示詞重翻一次。修「air ducts」偶爾漏翻
         成「氣 ducts」這種同碼不同結果的問題。"""
    def _call_llm(prompt_text: str) -> str:
        r = requests.post(f"{OLLAMA}/api/chat",
                          json={"model": LLM, "stream": False,
                                "options": {"temperature": 0.2},
                                "messages": [{"role": "user", "content": prompt_text}]},
                          timeout=30)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    try:
        prompt = ("把下面這句英文完整翻譯成繁體中文（台灣用語），一句自然的話，"
                  "不要清單、不要保留任何英文單字，複合詞和專有名詞也要整個翻成"
                  "中文意思（例如 air ducts 要翻成「空調風管」，不可以寫成「氣 "
                  f"ducts」）。英文：{english_desc}")
        with _llm_lock:
            for attempt in range(2):
                try:
                    zh_desc = _call_llm(prompt)
                    if attempt == 0 and re.search(r"[A-Za-z]{2,}", zh_desc):
                        # M54：偵測到翻譯結果還留有英文字，重翻一次
                        zh_desc = _call_llm(
                            f"你剛剛的翻譯還留有英文字沒翻：「{zh_desc}」，這是不允許"
                            f"的。請重新給我一句完整的繁體中文翻譯，把裡面每一個英文"
                            f"單字都換成對應的中文意思，整句不能出現任何英文字母。"
                            f"原文：{english_desc}"
                        )
                    return to_traditional(zh_desc)
                except requests.Timeout:
                    if attempt == 0:
                        time.sleep(0.5)
                    else:
                        raise
    except Exception as e:
        return f"[翻譯失敗: {str(e)[:30]}]"'''

assert src.count(OLD) == 1, "錨點數量變了，停止"
new_src = src.replace(OLD, NEW, 1)
assert new_src != src, "沒有變化，停止"
with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)
print(f"寫入完成：{path}（原本 {len(src)} 字元 -> 現在 {len(new_src)} 字元）")
PYEOF

echo "== [4/7] 語法檢查 =="
python3 -c "import ast; ast.parse(open('src/brain/server.py', encoding='utf-8').read())" && echo "server.py 語法 OK" || { echo "❌ 語法錯誤！立刻回復備份：cp src/brain/server.py.bak.$TS src/brain/server.py"; exit 1; }

echo "== [5/7] brain 是 image-build（非 bind mount），要重建映像檔才會生效 =="
docker compose build brain
docker compose up -d brain
echo "--- 等 brain 服務就緒 ---"
sleep 5
curl -sS http://127.0.0.1:${BRAIN_PORT:-21500}/health || true
echo ""

echo "== [6/7] 隔離測試：直接呼叫容器內的 _translate_vlm_to_zh()，繞過相機/VLM，"
echo "         用「原本會漏翻」的那種句子＋另外兩句，各測3次看穩不穩定 =="
docker compose exec -T brain python3 -c "
from server import _translate_vlm_to_zh
import re

tests = [
    'There are air ducts on the ceiling, blue walls with white text, gray floor, a person legs visible.',
    'A laptop and a coffee mug are on the wooden desk near the window.',
    'A red fire extinguisher is mounted on the wall next to the door.',
]

for t in tests:
    print('=== EN:', t)
    for i in range(3):
        zh = _translate_vlm_to_zh(t)
        leftover = re.findall(r'[A-Za-z]{2,}', zh)
        flag = '❌ 還有殘留英文: ' + str(leftover) if leftover else '✅ 無殘留英文'
        print(f'  第{i+1}次: {zh}   [{flag}]')
    print()
"

echo "== [7/7] git commit + push =="
git add src/brain/server.py
git status --short
git commit -m "M54: 修翻譯偶發不完整（同一輸入不同次翻譯結果不一致）

- 根因：_translate_vlm_to_zh() 提示詞太鬆、沒指定 temperature、
  翻完沒有任何檢查機制，qwen2.5:3b(3B) 偶爾會漏翻複合詞/專有名詞
  （例：\"air ducts\" 有時翻成「空調風管」，有時留成「氣 ducts」）
- 修法（只動這一個函式）：
  1. 提示詞明講複合詞/專有名詞也要整個翻，並舉例
  2. options.temperature 設 0.2，降低同輸入不同次結果不一致的機率
  3. 翻完用 regex 偵測殘留英文字母，若有就用更嚴格提示詞重翻一次
     （跟檔案裡既有的 _verify_no_hallucination 防幻覺檢查同一種精神）
- brain 是 image-build 服務（非 bind mount），這次改動有跑
  docker compose build brain 重建映像檔
- 用隔離測試（繞過相機/VLM，直接呼叫容器內的翻譯函式，同一句話
  測3次）驗證，而非只跑一次真實鏈路碰運氣

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
echo "M54 完成。請把 [6/7] 那一整段隔離測試的原始輸出全部貼給我"
echo "——尤其是有沒有出現「❌ 還有殘留英文」，以及同一句話3次的結果"
echo "是不是都合理、有沒有還是不穩定。這樣才能判斷這次修的有沒有用。"
echo "############################################################"
