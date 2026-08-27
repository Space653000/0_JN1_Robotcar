#!/usr/bin/env python3
"""
語音迴圈延遲分析版本

拆解四段延遲：
  1. 錄音（含 VAD 判斷停頓）
  2. ASR 轉文字
  3. Brain 意圖路由 + 生成回覆
  4. TTS 合成 + 播放

目標：定位瓶頸，為優化提供數據。
"""
import os
import sys
import time
import json
import logging
from datetime import datetime

import requests

BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:21500")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8004")
LOG_DIR = "data/vision_snapshots"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

os.makedirs(LOG_DIR, exist_ok=True)

# 模擬的 3 輪輸入
TEST_ROUNDS = [
    {"input": "你好"},
    {"input": "前面有什麼"},
    {"input": "結束對話"},
]


def simulate_listen(text: str) -> tuple:
    """
    模擬 ASR /listen，返回 (text, listen_ms)

    實際版本將調用真實 ASR，此版本用固定值模擬以便對比。
    """
    # 模擬錄音 + ASR 轉文字的延遲
    # 短文字（你好）: ~500ms
    # 長文字（前面有什麼）: ~800ms
    listen_ms = len(text) * 50 + 300  # 簡單估算
    time.sleep(listen_ms / 1000.0)
    return text, listen_ms


def ask_brain(text: str) -> tuple:
    """呼叫 brain /ask，計時 + 返回 (reply, intent, source, brain_ms)"""
    try:
        brain_start = time.time()
        r = requests.post(
            f"{BRAIN_URL}/ask",
            json={"text": text, "speak": False},
            timeout=30
        )
        brain_ms = (time.time() - brain_start) * 1000

        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            reply = data.get("reply", "")
            intent = data.get("intent", "unknown")
            source = data.get("source", "unknown")
            return reply, intent, source, brain_ms
        else:
            return "", "error", data.get("source", "error"), brain_ms
    except Exception as e:
        logger.error(f"❌ Brain 異常：{e}")
        return "", "error", "error", 0


def speak_reply(text: str) -> tuple:
    """呼叫 TTS /say，計時 + 返回 (success, tts_ms)"""
    try:
        tts_start = time.time()
        r = requests.post(
            f"{TTS_URL}/say",
            json={"text": text},
            timeout=120
        )
        tts_ms = (time.time() - tts_start) * 1000

        r.raise_for_status()
        data = r.json()
        return data.get("played", False), tts_ms
    except Exception as e:
        logger.error(f"❌ TTS 異常：{e}")
        return False, 0


def check_termination(text: str) -> bool:
    """檢查終止詞。"""
    termination_keywords = ["結束對話", "停止對話"]
    return any(kw in text for kw in termination_keywords)


def main():
    logger.info("=" * 80)
    logger.info("🎯 語音迴圈延遲分析 — 拆解四段延遲（錄音→ASR→腦部→TTS）")
    logger.info("=" * 80)

    # 初始化日誌
    log_file = f"{LOG_DIR}/voice_latency_log.txt"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"【M3-6b 語音迴圈延遲分析】\n")
        f.write(f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"目標：<4秒/輪\n\n")
        f.write(f"{'輪次':<4} {'錄音(ms)':<12} {'ASR(ms)':<12} {'腦部(ms)':<12} {'TTS(ms)':<12} {'總延遲(ms)':<15}\n")
        f.write(f"{'-'*80}\n")

    try:
        for turn, test_case in enumerate(TEST_ROUNDS, 1):
            heard = test_case["input"]
            logger.info(f"\n【第 {turn} 輪】輸入：{heard}")

            round_start = time.time()

            # 段 1：錄音 + ASR（此版本模擬，實際版本應調真實 ASR）
            logger.info("🎤 錄音 + ASR...")
            heard_result, listen_ms = simulate_listen(heard)

            # 段 2：Brain 意圖路由
            logger.info("🧠 Brain 路由...")
            reply, intent, source, brain_ms = ask_brain(heard)

            # 段 3：TTS 播放
            logger.info("🔊 TTS 播放...")
            played, tts_ms = speak_reply(reply) if reply else (False, 0)

            total_ms = (time.time() - round_start) * 1000

            # 記錄延遲
            logger.info(f"\n  ⏱️  錄音+ASR：{listen_ms:.0f}ms")
            logger.info(f"  ⏱️  Brain：{brain_ms:.0f}ms")
            logger.info(f"  ⏱️  TTS：{tts_ms:.0f}ms")
            logger.info(f"  ⏱️  【總延遲】{total_ms:.0f}ms（{total_ms/1000:.2f}s）")
            logger.info(f"  📝 意圖：{intent} | 來源：{source}")
            logger.info(f"  💬 回覆：{reply}")

            # 寫入日誌
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{turn:<4} {listen_ms:<12.0f} {brain_ms:<12.0f} {tts_ms:<12.0f} {total_ms:<15.0f}\n")

            # 檢查終止
            if check_termination(heard):
                logger.info("\n🛑 偵測終止詞")
                break

    except KeyboardInterrupt:
        logger.info("\n🛑 使用者中斷")
    except Exception as e:
        logger.error(f"\n❌ 異常：{e}")
        raise
    finally:
        logger.info("\n" + "=" * 80)
        logger.info("✅ 分析完成")
        logger.info(f"📋 詳細紀錄：{log_file}")
        logger.info("=" * 80)


if __name__ == "__main__":
    main()
