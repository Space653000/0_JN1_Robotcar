#!/usr/bin/env python3
"""
測試語音迴圈 — 模擬 4 輪對話

此腳本跳過實際 ASR（語音轉文字），直接測試：
  Brain 意圖路由 → TTS 播放

模擬輸入：
  1. "你好" → faq_name 意圖 → 語音回招呼
  2. "前面有什麼" → state 意圖 → 語音講出看到什麼（perception-natural）
  3. "你叫什麼" → faq_name 意圖 → 語音回 JN1
  4. "結束對話" → 停止迴圈
"""
import os
import sys
import time
import json
import logging
from datetime import datetime

import requests

# 配置
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

# 模擬的 4 輪輸入
TEST_ROUNDS = [
    {"input": "你好", "expected_intent": "faq_name"},
    {"input": "前面有什麼", "expected_intent": "state"},
    {"input": "你叫什麼", "expected_intent": "faq_name"},
    {"input": "結束對話", "expected_intent": "chat"},
]


def ask_brain(text: str) -> tuple:
    """呼叫 brain /ask 進行意圖路由 + 生成回覆。"""
    try:
        logger.info(f"🧠 呼叫 Brain /ask...")
        r = requests.post(
            f"{BRAIN_URL}/ask",
            json={"text": text, "speak": False},
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            reply = data.get("reply", "")
            intent = data.get("intent", "unknown")
            source = data.get("source", "unknown")
            logger.info(f"✅ 意圖：{intent} | 來源：{source}")
            logger.info(f"💬 回覆：{reply}")
            return reply, intent, source
        else:
            logger.error(f"❌ Brain 返回失敗")
            return "", "error", data.get("source", "error")
    except Exception as e:
        logger.error(f"❌ Brain 呼叫異常：{e}")
        return "", "error", "error"


def speak_reply(text: str) -> bool:
    """呼叫 TTS /say 播放回覆。"""
    try:
        logger.info("🔊 TTS 播放回覆...")
        start = time.time()
        r = requests.post(
            f"{TTS_URL}/say",
            json={"text": text},
            timeout=120
        )
        r.raise_for_status()
        data = r.json()
        elapsed = time.time() - start

        if data.get("played"):
            logger.info(f"✅ TTS 播放完成（{elapsed:.1f}s）")
            return True
        else:
            logger.warning(f"⚠️  TTS 未播放")
            return False
    except Exception as e:
        logger.error(f"❌ TTS 呼叫異常：{e}")
        return False


def log_round(turn: int, heard: str, intent: str, reply: str, elapsed: float):
    """記錄逐輪到日誌。"""
    msg = (f"【第 {turn} 輪】\n"
           f"  聽到：{heard}\n"
           f"  意圖：{intent}\n"
           f"  回覆：{reply}\n"
           f"  延遲：{elapsed:.2f}s\n")
    logger.info(msg)
    with open(f"{LOG_DIR}/voice_loop_log.txt", "a", encoding="utf-8") as f:
        f.write(msg)


def check_termination(text: str) -> bool:
    """檢查是否是終止詞。"""
    termination_keywords = ["結束對話", "结束对话", "停止", "停止对话"]
    return any(kw in text for kw in termination_keywords)


def main():
    logger.info("=" * 70)
    logger.info("🤖 語音迴圈測試 — 4 輪自動化測試（模擬用戶輸入）")
    logger.info("=" * 70)

    # 清空日誌
    with open(f"{LOG_DIR}/voice_loop_log.txt", "w", encoding="utf-8") as f:
        f.write(f"【M3-6 語音迴圈測試】\n時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    try:
        for turn, test_case in enumerate(TEST_ROUNDS, 1):
            heard = test_case["input"]
            logger.info(f"\n【第 {turn} 輪】")
            logger.info(f"📢 模擬用戶輸入：{heard}")

            # 呼叫 Brain
            round_start = time.time()
            reply, intent, source = ask_brain(heard)

            # TTS 播放
            if reply:
                speak_reply(reply)
            else:
                logger.warning("⚠️  沒有回覆內容")

            elapsed = time.time() - round_start

            # 記錄
            log_round(turn, heard, intent, reply, elapsed)

            # 檢查終止
            if check_termination(heard):
                logger.info("🛑 檢測到終止詞，測試停止")
                break

            # 輪間延遲
            if turn < len(TEST_ROUNDS):
                time.sleep(1)

    except Exception as e:
        logger.error(f"❌ 測試異常：{e}")
        raise
    finally:
        logger.info("\n" + "=" * 70)
        logger.info("✅ 測試完成")
        logger.info(f"📋 詳細紀錄存於：{LOG_DIR}/voice_loop_log.txt")
        logger.info("=" * 70)


if __name__ == "__main__":
    main()
