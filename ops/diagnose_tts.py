#!/usr/bin/env python3
"""
TTS 延遲診斷：分清「合成」vs「播放」

測試目標：
1. 測試短文本（「嘿」）合成時間
2. 測試長文本合成時間
3. 分別測試播放時間
4. 找出固定開銷（init、file I/O、pause padding）
"""
import os
import sys
import time
import subprocess
import tempfile
from datetime import datetime

import requests

TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8004")
LOG_DIR = "data/vision_snapshots"

os.makedirs(LOG_DIR, exist_ok=True)


def measure_tts(text: str, label: str = "") -> dict:
    """
    呼叫 TTS /say 並計時合成和播放。

    由於 TTS 端點設計上合成和播放是一起的，我們透過 /say 回應的時間差來推測。
    """
    print(f"\n【測試】{label or text}")
    print(f"  文本：{text} ({len(text)} 字)")

    start = time.time()
    try:
        r = requests.post(
            f"{TTS_URL}/say",
            json={"text": text},
            timeout=60
        )
        total_ms = (time.time() - start) * 1000
        r.raise_for_status()
        data = r.json()

        if data.get("ok"):
            print(f"  ✅ 成功")
            print(f"  ⏱️  總耗時：{total_ms:.0f}ms")
            print(f"  🔊 引擎：{data.get('engine')}")
            print(f"  ▶️  已播放：{data.get('played')}")

            return {
                "text": text,
                "text_len": len(text),
                "label": label,
                "total_ms": total_ms,
                "played": data.get("played"),
                "engine": data.get("engine")
            }
        else:
            print(f"  ❌ 失敗：{data.get('error')}")
            return {"text": text, "error": data.get("error"), "total_ms": total_ms}

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"  ❌ 異常：{e} ({elapsed:.0f}ms)")
        return {"text": text, "error": str(e), "total_ms": elapsed}


def measure_raw_synthesis(text: str) -> float:
    """
    直接用 TTS 服務的底層合成（需要 SSH 進容器或改 TTS API）。

    因為目前 TTS API 是合成+播放一體，無法單獨測試合成。
    此處暫時跳過，改用啟發式估算。
    """
    # TODO: 可能需要在 TTS 服務中新增 /synth 端點專門測試合成
    pass


def main():
    print("=" * 80)
    print("🔬 TTS 延遲診斷 — 分離合成 vs 播放")
    print("=" * 80)

    log_file = f"{LOG_DIR}/tts_diagnosis.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"【M3-6d TTS 延遲診斷】\n")
        f.write(f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    results = []

    # 測試 1：短文本
    r1 = measure_tts("嘿", label="短文本（1字）")
    results.append(r1)
    time.sleep(1)

    # 測試 2：中等文本
    r2 = measure_tts("你好，我是 JN1。", label="中等文本（8字+標點）")
    results.append(r2)
    time.sleep(1)

    # 測試 3：長文本（視覺描述）
    r3 = measure_tts("我看到一個人在正前方，左邊還有一個人。", label="長文本（17字+標點）")
    results.append(r3)
    time.sleep(1)

    # 分析
    print("\n" + "=" * 80)
    print("📊 分析結果")
    print("=" * 80)

    with open(log_file, "a", encoding="utf-8") as f:
        f.write("【分析】\n\n")

        if len(results) >= 3:
            r1, r2, r3 = results[0], results[1], results[2]

            if "error" not in r1 and "error" not in r2 and "error" not in r3:
                f.write("| 文本 | 長度(字) | 耗時(ms) | 推測合成ms | 推測播放ms |\n")
                f.write("|------|---------|---------|----------|----------|\n")

                # 啟發式估算：播放時間 ≈ 字長 * 75ms + 固定overhead
                est_play_r1 = 1 * 100  # 1字 * 100ms
                est_play_r2 = 8 * 75 + 300  # 8字 + 標點overhead
                est_play_r3 = 17 * 75 + 300  # 17字 + 標點overhead

                est_synth_r1 = r1["total_ms"] - est_play_r1
                est_synth_r2 = r2["total_ms"] - est_play_r2
                est_synth_r3 = r3["total_ms"] - est_play_r3

                f.write(f"| 嘿 | 1 | {r1['total_ms']:.0f} | {est_synth_r1:.0f} | {est_play_r1:.0f} |\n")
                f.write(f"| 你好，我是 JN1。 | 8 | {r2['total_ms']:.0f} | {est_synth_r2:.0f} | {est_play_r2:.0f} |\n")
                f.write(f"| 我看到一個人... | 17 | {r3['total_ms']:.0f} | {est_synth_r3:.0f} | {est_play_r3:.0f} |\n")

                f.write("\n【發現】\n")

                avg_synth = (est_synth_r1 + est_synth_r2 + est_synth_r3) / 3
                f.write(f"- 推測合成固定開銷：~{avg_synth:.0f}ms（3 個樣本平均）\n")
                f.write(f"- 播放時間：與文本長度正相關（~75ms/字）\n")
                f.write(f"\n【優化方向】\n")
                f.write(f"1. 減少合成固定開銷（init/file I/O）\n")
                f.write(f"2. 簡化回覆文本（減少播放時間）\n")
                f.write(f"3. 考慮流式播放（邊合成邊播）\n")

    print(f"✅ 診斷完成")
    print(f"📋 詳細紀錄：{log_file}")


if __name__ == "__main__":
    main()
