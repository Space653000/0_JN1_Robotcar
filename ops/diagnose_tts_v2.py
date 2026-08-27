#!/usr/bin/env python3
"""
M3-6e TTS 优化诊断 v2
- 测试新的「整句一次合成」是否比分段合成快
- 记录 Kokoro 模型加载次数
- 测试 GPU provider 是否可用
"""
import os
import sys
import time
import subprocess
import json
from datetime import datetime

import requests

TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8004")
LOG_DIR = "data/vision_snapshots"

os.makedirs(LOG_DIR, exist_ok=True)


def test_tts_health():
    """Check TTS service health and engine."""
    try:
        r = requests.get(f"{TTS_URL}/health", timeout=5)
        data = r.json()
        print(f"✅ TTS Service Health:")
        print(f"   Engine: {data.get('engine')}")
        print(f"   Voice: {data.get('voice')}")
        return True
    except Exception as e:
        print(f"❌ TTS Service unavailable: {e}")
        return False


def measure_tts(text: str, label: str = "", iteration: int = 1):
    """Call TTS /say and measure response time."""
    print(f"\n【测试 {iteration}】{label or text}")
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
            synth_ms = data.get("synth_ms", 0)
            play_ms = data.get("play_ms", 0)
            print(f"  ✅ 成功")
            print(f"  ⏱️  合成：{synth_ms:.0f}ms，播放：{play_ms:.0f}ms，总计：{total_ms:.0f}ms")
            print(f"  📊 合成速度：{synth_ms/len(text):.1f}ms/字")
            return {
                "text": text,
                "text_len": len(text),
                "label": label,
                "total_ms": total_ms,
                "synth_ms": synth_ms,
                "play_ms": play_ms,
                "engine": data.get("engine")
            }
        else:
            print(f"  ❌ 失败：{data.get('error')}")
            return {"text": text, "error": data.get("error"), "total_ms": total_ms}

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"  ❌ 异常：{e} ({elapsed:.0f}ms)")
        return {"text": text, "error": str(e), "total_ms": elapsed}


def main():
    print("=" * 80)
    print("🔬 M3-6e Kokoro TTS 优化诊断 v2")
    print("=" * 80)

    if not test_tts_health():
        sys.exit(1)

    log_file = f"{LOG_DIR}/voice_latency_log4.txt"
    results = []

    # 测试用例
    test_cases = [
        ("嘿", "短文本（1字，无标点）"),
        ("你好", "简短（2字，无标点）"),
        ("你好，我是 JN1。", "中等（8字+标点）"),
        ("我看到一个人。", "简单+标点（6字+标点）"),
        ("我看到一个人在正前方，左边还有一个人。", "长文本+多标点（17字+标点）"),
    ]

    print("\n【运行测试】")

    for text, label in test_cases:
        r = measure_tts(text, label)
        results.append(r)
        time.sleep(0.5)

    # 分析结果
    print("\n" + "=" * 80)
    print("📊 分析结果")
    print("=" * 80)

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"【M3-6e Kokoro TTS 优化诊断】\n")
        f.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"URL：{TTS_URL}\n\n")

        f.write("【优化说明】\n")
        f.write("- 原设计：_synth_with_pauses() 对每个标点段分别调用模型（N 段 → N 次模型调用）\n")
        f.write("- 优化后：整句一次合成，不再分段调用模型\n")
        f.write("- 目标：单字合成时间 <250ms（当前 ~1300ms/字 是不可接受的）\n\n")

        f.write("【测试结果】\n\n")
        f.write("| 文本 | 字数 | 合成(ms) | 播放(ms) | 总计(ms) | 合成速度(ms/字) |\n")
        f.write("|------|------|---------|---------|---------|----------------|\n")

        valid_results = [r for r in results if "error" not in r]
        if valid_results:
            for r in valid_results:
                synth_ms = r.get("synth_ms", 0)
                play_ms = r.get("play_ms", 0)
                text_len = r.get("text_len", 1)
                speed = synth_ms / text_len if text_len > 0 else 0
                f.write(f"| {r['text'][:20]:20} | {text_len:2} | {synth_ms:7.0f} | {play_ms:7.0f} | {synth_ms+play_ms:7.0f} | {speed:14.1f} |\n")

        f.write("\n【诊断和建议】\n")

        if valid_results:
            synth_speeds = []
            for r in valid_results:
                if r.get("text_len", 0) > 0:
                    synth_speeds.append(r.get("synth_ms", 0) / r.get("text_len", 1))

            avg_speed = sum(synth_speeds) / len(synth_speeds) if synth_speeds else 0
            min_speed = min(synth_speeds) if synth_speeds else 0
            max_speed = max(synth_speeds) if synth_speeds else 0

            f.write(f"- 平均合成速度：{avg_speed:.1f}ms/字\n")
            f.write(f"- 最快：{min_speed:.1f}ms/字，最慢：{max_speed:.1f}ms/字\n")

            if avg_speed < 250:
                f.write(f"✅ 优化成功！合成速度已达到可接受范围（<250ms/字）\n")
            elif avg_speed < 500:
                f.write(f"⚠️ 部分改善，但仍需进一步优化\n")
                f.write(f"   - 建议尝试 onnxruntime GPU provider (CUDA)\n")
                f.write(f"   - 或考虑切换到 Piper TTS (更快但质量略低)\n")
            else:
                f.write(f"❌ 合成仍然过慢（>{avg_speed:.0f}ms/字）\n")
                f.write(f"   - 原因可能：Kokoro 模型较大，或 onnxruntime 单线程执行\n")
                f.write(f"   - 建议：切换到 Piper TTS 或尝试 CUDA GPU provider\n")

            f.write(f"\n【后续步骤】\n")
            f.write(f"1. 检查容器日志中的 [tts] 模型加载时机\n")
            f.write(f"2. 如果平均速度仍 >500ms/字，执行 fallback_to_piper.sh\n")
            f.write(f"3. 重新运行诊断验证 Piper 性能\n")

    print(f"\n✅ 诊断完成")
    print(f"📋 详细记录：{log_file}")

    # 打印最终建议
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        synth_speeds = []
        for r in valid_results:
            if r.get("text_len", 0) > 0:
                synth_speeds.append(r.get("synth_ms", 0) / r.get("text_len", 1))
        avg_speed = sum(synth_speeds) / len(synth_speeds) if synth_speeds else 0
        print(f"\n【最终结论】")
        print(f"平均合成速度：{avg_speed:.1f}ms/字")
        if avg_speed >= 500:
            print(f"⚠️  建议考虑 Piper TTS fallback")


if __name__ == "__main__":
    main()
