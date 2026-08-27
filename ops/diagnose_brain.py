#!/usr/bin/env python3
"""
診斷腦部延遲瓶頸

記錄：
1. 一輪對話中調用了幾次 qwen
2. 每次 qwen 調用的延遲（包括加載時間）
3. ollama 日誌中是否有「loading model」
4. ollama ps 中 qwen 是否持續常駐
"""
import os
import time
import json
import subprocess
from datetime import datetime

import requests

BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:21500")
LOG_DIR = "data/vision_snapshots"

os.makedirs(LOG_DIR, exist_ok=True)

# 全局變數追蹤 qwen 呼叫
_qwen_calls = []

# Monkey-patch requests.post 來追蹤 ollama 呼叫
_original_post = requests.post

def _patched_post(url, *args, **kwargs):
    if "ollama" in url and "/api/chat" in url:
        print(f"  📝 [qwen] 呼叫開始...")
        call_start = time.time()
        try:
            result = _original_post(url, *args, **kwargs)
            elapsed = (time.time() - call_start) * 1000
            _qwen_calls.append({"url": url, "elapsed_ms": elapsed, "status": "ok"})
            print(f"  ✅ [qwen] 完成 ({elapsed:.0f}ms)")
            return result
        except Exception as e:
            elapsed = (time.time() - call_start) * 1000
            _qwen_calls.append({"url": url, "elapsed_ms": elapsed, "status": f"error: {e}"})
            print(f"  ❌ [qwen] 失敗 ({elapsed:.0f}ms): {e}")
            raise
    else:
        return _original_post(url, *args, **kwargs)

requests.post = _patched_post


def test_round(text: str) -> dict:
    """測試一輪對話並記錄 qwen 呼叫."""
    global _qwen_calls
    _qwen_calls = []  # 重置計數

    round_start = time.time()
    print(f"\n【測試】{text}")
    print(f"  🕐 開始時間：{datetime.now().strftime('%H:%M:%S.%f')[:-3]}")

    try:
        r = requests.post(
            f"{BRAIN_URL}/ask",
            json={"text": text, "speak": False},
            timeout=30
        )
        r.raise_for_status()
        data = r.json()

        elapsed = (time.time() - round_start) * 1000
        qwen_count = len(_qwen_calls)
        qwen_total_ms = sum(c["elapsed_ms"] for c in _qwen_calls)

        print(f"  ✅ 回覆：{data.get('reply')}")
        print(f"  📊 意圖：{data.get('intent')} | 來源：{data.get('source')}")
        print(f"  ⏱️  總耗時：{elapsed:.0f}ms")
        print(f"  🧠 qwen 呼叫數：{qwen_count}")
        if qwen_count > 0:
            print(f"  🧠 qwen 總耗時：{qwen_total_ms:.0f}ms")
            for i, call in enumerate(_qwen_calls, 1):
                print(f"     - 呼叫 {i}：{call['elapsed_ms']:.0f}ms ({call['status']})")

        return {
            "text": text,
            "reply": data.get("reply"),
            "intent": data.get("intent"),
            "source": data.get("source"),
            "total_ms": elapsed,
            "qwen_count": qwen_count,
            "qwen_total_ms": qwen_total_ms,
            "qwen_calls": _qwen_calls.copy()
        }
    except Exception as e:
        elapsed = (time.time() - round_start) * 1000
        print(f"  ❌ 失敗：{e}")
        return {
            "text": text,
            "error": str(e),
            "total_ms": elapsed,
            "qwen_count": len(_qwen_calls),
            "qwen_total_ms": sum(c["elapsed_ms"] for c in _qwen_calls)
        }


def check_ollama_ps():
    """檢查 ollama ps 中是否有 qwen."""
    try:
        output = subprocess.check_output(["docker", "exec", "robotcar-ollama-new-1", "ollama", "ps"],
                                         text=True)
        print(f"\n【ollama ps】")
        print(output)
        return "qwen" in output
    except Exception as e:
        print(f"⚠️  ollama ps 失敗：{e}")
        return None


def main():
    print("=" * 80)
    print("🔬 腦部延遲診斷 — 追蹤 qwen 呼叫次數和延遲")
    print("=" * 80)

    # 初始化日誌
    log_file = f"{LOG_DIR}/brain_diagnosis.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"【M3-6c 腦部延遲診斷】\n")
        f.write(f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    results = []

    try:
        # 測試 3 輪
        test_cases = ["你好", "前面有什麼", "結束對話"]

        for text in test_cases:
            result = test_round(text)
            results.append(result)

            # 檢查 ollama ps
            if "前面有什麼" in text:
                qwen_resident = check_ollama_ps()
                if qwen_resident:
                    print("✅ qwen 常駐中")
                else:
                    print("❌ qwen 未常駐（可能被驅逐或重載）")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 使用者中斷")
    except Exception as e:
        print(f"\n❌ 異常：{e}")
        raise
    finally:
        print("\n" + "=" * 80)
        print("📋 結果總結")
        print("=" * 80)

        # 寫入日誌
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("【測試結果】\n\n")
            for result in results:
                if "error" not in result:
                    f.write(f"【{result['text']}】\n")
                    f.write(f"  回覆：{result['reply']}\n")
                    f.write(f"  意圖：{result['intent']} | 來源：{result['source']}\n")
                    f.write(f"  總耗時：{result['total_ms']:.0f}ms\n")
                    f.write(f"  qwen 呼叫數：{result['qwen_count']}\n")
                    f.write(f"  qwen 總耗時：{result['qwen_total_ms']:.0f}ms\n")
                    if result['qwen_calls']:
                        for i, call in enumerate(result['qwen_calls'], 1):
                            f.write(f"    - 呼叫 {i}：{call['elapsed_ms']:.0f}ms\n")
                    f.write("\n")
                else:
                    f.write(f"【{result['text']}】❌ {result['error']}\n\n")

        print(f"✅ 診斷完成")
        print(f"📋 詳細紀錄：{log_file}")

        # 統計
        total_qwen_calls = sum(r.get("qwen_count", 0) for r in results)
        print(f"\n【統計】")
        print(f"總 qwen 呼叫次數：{total_qwen_calls}")
        avg_qwen_ms = sum(r.get("qwen_total_ms", 0) for r in results) / max(1, total_qwen_calls)
        print(f"平均 qwen 延遲：{avg_qwen_ms:.0f}ms/次")


if __name__ == "__main__":
    main()
