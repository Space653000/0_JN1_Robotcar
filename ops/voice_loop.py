#!/usr/bin/env python3
"""
robotcar voice loop — 喚醒詞 + 即時語音對話迴圈

設計（V2 — 喚醒詞版本）：
  待命階段（STANDBY）：
    1. 短錄音 2 秒（輕量待命）
    2. ASR 轉文字
    3. 檢查喚醒詞（「嘿JN1」、「JN1」、「機器人」）
    4. 若無喚醒詞 → 回到待命；有 → 進入對話

  對話階段（ACTIVE）：
    1. 回覆「我在」或嗶聲
    2. 錄音 5 秒（指令）
    3. ASR 轉文字
    4. Brain /ask 路由判斷 + 生成回覆
    5. TTS 播放（期間暫停收音，避免自回授）
    6. 靜默超時或偵測終止詞 → 回到待命
    7. 否則回到步驟 2

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
STANDBY_SECONDS = 2  # 待命時短錄音
LOG_DIR = "data/vision_snapshots"

# 喚醒詞
WAKEWORDS = ["嘿jn1", "hey jn1", "jn1", "機器人", "机器人"]

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


def is_wakeword(text: str) -> bool:
    """檢查是否包含喚醒詞。"""
    text_lower = text.lower().strip()
    # 檢查是否包含任何喚醒詞（模糊匹配，避免口音差異）
    for ww in WAKEWORDS:
        if ww in text_lower:
            return True
    return False


def check_termination(text: str) -> bool:
    """檢查是否是終止詞。"""
    termination_keywords = ["結束對話", "结束对话", "停止", "停止对话", "退出", "再見", "再见", "bye", "exit"]
    text_lower = text.lower()
    return any(kw in text_lower for kw in termination_keywords)


def standby_listen() -> str:
    """
    待命模式：短錄音 + ASR，返回聽到的文字或空字串。
    """
    try:
        logger.info(f"🎤 待命中...（{STANDBY_SECONDS}秒短錄音）")
        r = requests.post(f"{ASR_URL}/listen", params={"seconds": STANDBY_SECONDS}, timeout=STANDBY_SECONDS + 30)
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            text = data.get("text", "").strip()
            if text:
                return text
        return ""
    except Exception as e:
        logger.debug(f"⚠️  待命錄音異常：{e}")
        return ""


def wakeup_response() -> bool:
    """
    喚醒後的應答：播放「我在」或嗶聲。
    """
    try:
        logger.info("🔊 喚醒應答中...")
        r = requests.post(
            f"{TTS_URL}/say",
            json={"text": "我在"},
            timeout=120
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"⚠️  喚醒應答失敗：{e}")
        return False


def main():
    """
    主迴圈 V2：
    待命 → 喚醒詞偵測 → 喚醒應答 → 對話迴圈 → 回到待命
    """
    logger.info("=" * 60)
    logger.info("🤖 語音迴圈啟動（喚醒詞版本）")
    logger.info(f"   喚醒詞：{' / '.join(WAKEWORDS)}")
    logger.info("   說『結束對話』回到待命或停止程序")
    logger.info("=" * 60)

    # 清空日誌
    with open(f"{LOG_DIR}/voice_loop_log.txt", "w", encoding="utf-8") as f:
        f.write(f"【Voice Loop V2 — 喚醒詞版本】\n時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    wakeup_attempts = 0
    false_wakeups = 0
    conversation_turns = 0

    try:
        while True:
            # ======================== 待命階段 ========================
            logger.info("\n【待命中...】（喊『嘿JN1』喚醒）")

            # 待命短錄音
            heard = standby_listen()

            if not heard:
                continue

            # 檢查喚醒詞
            if not is_wakeword(heard):
                logger.info(f"🔇 非喚醒詞，繼續待命：{heard}")
                false_wakeups += 1
                continue

            # ======================== 偵測到喚醒詞 ========================
            wakeup_attempts += 1
            logger.info(f"\n🎯 【喚醒成功】#{wakeup_attempts}：{heard}")

            # 喚醒應答
            wakeup_response()

            # ======================== 對話階段 ========================
            logger.info("【進入對話模式】（說你的指令，靜默 10 秒自動回待命）")

            conversation_turns = 0
            idle_time = 0

            while True:
                conversation_turns += 1
                logger.info(f"\n【對話輪次：{conversation_turns}】")

                # 對話時長錄音
                heard = listen_and_transcribe(LISTEN_SECONDS)

                # 靜默 → 超時退出
                if not heard:
                    idle_time += LISTEN_SECONDS
                    if idle_time >= 10:
                        logger.info(f"⏱️  靜默超過 10 秒，回到待命")
                        break
                    logger.info(f"🔇 靜默 {idle_time}s，繼續等待...")
                    continue

                idle_time = 0

                # 檢查終止詞
                if check_termination(heard):
                    logger.info("🛑 偵測終止詞，回到待命")
                    break

                # 腦部判斷
                round_start = time.time()
                reply, intent, source = ask_brain(heard)

                # TTS 播放
                if reply:
                    speak_reply(reply)
                else:
                    logger.warning("⚠️  沒有回覆內容")

                elapsed = time.time() - round_start

                # 記錄逐輪
                log_entry(f"{wakeup_attempts}-{conversation_turns}", heard, intent, reply, elapsed)

            # 回到待命
            logger.info("【回到待命】\n")

    except KeyboardInterrupt:
        logger.info("\n🛑 使用者中斷（Ctrl+C），迴圈停止")
    except Exception as e:
        logger.error(f"\n❌ 迴圈異常：{e}")
        raise
    finally:
        logger.info("=" * 60)
        logger.info("✅ 語音迴圈結束")
        logger.info(f"📊 統計：")
        logger.info(f"   喚醒成功：{wakeup_attempts} 次")
        logger.info(f"   誤喚醒：{false_wakeups} 次")
        if wakeup_attempts > 0:
            logger.info(f"   喚醒成功率：{100*wakeup_attempts/(wakeup_attempts+false_wakeups):.1f}%")
        logger.info(f"📋 詳細紀錄存於：{LOG_DIR}/voice_loop_log.txt")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
