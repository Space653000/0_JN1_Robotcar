#!/usr/bin/env python3
"""
robotcar voice loop — 即時語音對話迴圈

設計：
  1. 迴圈錄音 5 秒（或 VAD 偵測到靜默）
  2. ASR 轉文字
  3. Brain /ask 路由判斷 + 生成回覆
  4. TTS 播放（期間暫停收音，避免自回授）
  5. 檢查終止詞，無則回到步驟 1

防回授：TTS 播放期間完全暫停收音，避免 bot 誤把自己的聲音當成用戶輸入。

使用：python3 ops/voice_loop.py
"""
import os
import sys
import time
import json
import logging
import subprocess
from datetime import datetime

import requests

# 配置
ASR_URL = os.environ.get("ASR_URL", "http://127.0.0.1:8003")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:21500")
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:8004")
LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "5"))
LOG_DIR = "data/vision_snapshots"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

os.makedirs(LOG_DIR, exist_ok=True)


def log_entry(turn: int, heard: str, intent: str, reply: str, elapsed: float):
    """記錄逐輪交互到日誌。"""
    msg = (f"【第 {turn} 輪】"
           f"\n  聽到：{heard}"
           f"\n  意圖：{intent}"
           f"\n  回覆：{reply}"
           f"\n  延遲：{elapsed:.2f}s\n")
    logger.info(msg)
    with open(f"{LOG_DIR}/voice_loop_log.txt", "a", encoding="utf-8") as f:
        f.write(msg)


def listen_and_transcribe(seconds: int = LISTEN_SECONDS) -> str:
    """
    呼叫 ASR /listen 錄音並轉文字。

    Returns: 轉錄的文字（如果失敗或無輸入則返回空字串）
    """
    try:
        logger.info(f"🎤 錄音中...({seconds}秒)")
        r = requests.post(f"{ASR_URL}/listen", params={"seconds": seconds}, timeout=seconds + 30)
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            text = data.get("text", "").strip()
            if text:
                logger.info(f"📝 聽到：{text}")
                return text
            else:
                logger.info("🔇 沒有輸入（靜默或雜音）")
                return ""
        else:
            logger.error(f"❌ ASR 失敗：{data.get('error')}")
            return ""
    except Exception as e:
        logger.error(f"❌ ASR 呼叫異常：{e}")
        return ""


def ask_brain(text: str) -> tuple:
    """
    呼叫 brain /ask 進行意圖路由 + 生成回覆。

    Returns: (reply, intent, source) 或 異常則 ("", "error", "error")
    """
    try:
        r = requests.post(
            f"{BRAIN_URL}/ask",
            json={"text": text, "speak": False},  # speak=False 因為我們自己用 TTS
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            reply = data.get("reply", "")
            intent = data.get("intent", "unknown")
            source = data.get("source", "unknown")
            logger.info(f"🧠 意圖：{intent} | 來源：{source}")
            logger.info(f"💬 回覆：{reply}")
            return reply, intent, source
        else:
            logger.error(f"❌ Brain 返回失敗：{data}")
            return "", "error", data.get("source", "error")
    except Exception as e:
        logger.error(f"❌ Brain 呼叫異常：{e}")
        return "", "error", "error"


def speak_reply(text: str) -> bool:
    """
    呼叫 TTS /say 播放回覆。

    此期間應暫停錄音（防回授），但由於 /listen 是阻塞式呼叫，
    實際上只要在下一輪錄音前完成播放即可。

    Returns: 播放成功 True/False
    """
    try:
        logger.info("🔊 TTS 播放中（暫停收音以防回授）...")
        start = time.time()
        r = requests.post(
            f"{TTS_URL}/say",
            json={"text": text},
            timeout=120  # TTS 可能較慢
        )
        r.raise_for_status()
        data = r.json()
        elapsed = time.time() - start

        if data.get("played"):
            logger.info(f"✅ TTS 播放完成（{elapsed:.1f}s）")
            return True
        else:
            logger.warning(f"⚠️  TTS 未播放：{data.get('error')}")
            return False
    except Exception as e:
        logger.error(f"❌ TTS 呼叫異常：{e}")
        return False


def check_termination(text: str) -> bool:
    """檢查是否是終止詞。"""
    termination_keywords = ["結束對話", "结束对话", "停止", "停止对话", "退出", "再見", "再见", "bye", "exit"]
    text_lower = text.lower()
    return any(kw in text_lower for kw in termination_keywords)


def main():
    """主迴圈：錄音 → ASR → Brain → TTS → 檢查終止。"""
    logger.info("=" * 60)
    logger.info("🤖 語音迴圈啟動 — 開口就能對話（說『結束對話』停止）")
    logger.info("=" * 60)

    # 清空日誌
    with open(f"{LOG_DIR}/voice_loop_log.txt", "w", encoding="utf-8") as f:
        f.write(f"【M3-6 語音迴圈實測】\n時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    turn = 0
    try:
        while True:
            turn += 1
            logger.info(f"\n【第 {turn} 輪】")

            # 步驟 1：錄音 + ASR
            heard = listen_and_transcribe()

            # 空白輸入不打擾，直接回到聽
            if not heard:
                continue

            # 步驟 2：腦部判斷
            round_start = time.time()
            reply, intent, source = ask_brain(heard)

            # 步驟 3：TTS 播放（此期間防回授）
            if reply:
                speak_reply(reply)
            else:
                logger.warning("⚠️  沒有回覆內容，跳過 TTS")

            elapsed = time.time() - round_start

            # 記錄逐輪
            log_entry(turn, heard, intent, reply, elapsed)

            # 步驟 4：檢查終止詞
            if check_termination(heard):
                logger.info("\n🛑 檢測到終止詞，迴圈停止")
                break

    except KeyboardInterrupt:
        logger.info("\n🛑 使用者中斷（Ctrl+C），迴圈停止")
    except Exception as e:
        logger.error(f"\n❌ 迴圈異常：{e}")
        raise
    finally:
        logger.info("=" * 60)
        logger.info("✅ 語音迴圈結束")
        logger.info(f"📋 詳細紀錄存於：{LOG_DIR}/voice_loop_log.txt")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
