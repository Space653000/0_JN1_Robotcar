#!/usr/bin/env python3
# jn1_tts_player.py — 在 J4012 主機上，把 TTS 產生的語音播到你插在機器上的耳機。
#
# 為什麼需要它：
#   TTS 服務跑在 Docker 容器裡，容器碰不到主機的 PulseAudio（容器內 paplay 會
#   回 "Access denied"）。但容器會把合成好的 wav 寫到共用資料夾 data/logs，
#   而主機以 jetson 身分跑 paplay 是可以正常出聲的。
#   所以這支在「主機、jetson 使用者、有音效工作階段」的環境裡跑，監看那個資料夾，
#   一有新語音就由主機播放 → 傳到你插在 J4012 上的耳機。
#
# 用法：
#   nohup python3 jn1_tts_player.py > /tmp/jn1_tts_player.log 2>&1 &
# 環境變數（都可不填）：
#   JN1_TTS_LOGDIR  預設 ~/0_JN1_Robotcar/data/logs
#   JN1_TTS_SINK    指定音效輸出裝置名稱；留空=系統預設（你的耳機）
#   JN1_TTS_POLL    掃描間隔秒數，預設 0.25

import os, time, glob, subprocess

LOGDIR  = os.environ.get("JN1_TTS_LOGDIR", os.path.expanduser("~/0_JN1_Robotcar/data/logs"))
POLL    = float(os.environ.get("JN1_TTS_POLL", "0.25"))
SINK    = os.environ.get("JN1_TTS_SINK", "").strip()
PATTERN = os.path.join(LOGDIR, "tts_*.wav")

played = set()
# 啟動時把「現有的」舊語音檔標記成已處理，避免一開機把歷史語音全部重播一遍。
for f in glob.glob(PATTERN):
    played.add(f)
print(f"[jn1-tts-player] 監看 {PATTERN}；啟動時既有 {len(played)} 檔（略過不播）", flush=True)
if SINK:
    print(f"[jn1-tts-player] 指定輸出裝置：{SINK}", flush=True)


def stable(path):
    """確認檔案已寫完：兩次取檔案大小一致、且大於 WAV 標頭(44 bytes)。"""
    try:
        s1 = os.path.getsize(path)
        time.sleep(POLL)
        s2 = os.path.getsize(path)
    except OSError:
        return False
    return s1 == s2 and s2 > 44


def play(path):
    cmd = ["paplay"] + (["--device", SINK] if SINK else []) + [path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            print(f"[jn1-tts-player] ▶ 播放 {os.path.basename(path)}", flush=True)
        else:
            print(f"[jn1-tts-player] ✗ {os.path.basename(path)} rc={r.returncode} "
                  f"{r.stderr.strip()}", flush=True)
    except Exception as e:
        print(f"[jn1-tts-player] ✗ {os.path.basename(path)} {e}", flush=True)


print("[jn1-tts-player] 開始監看…", flush=True)
while True:
    try:
        for f in sorted(glob.glob(PATTERN)):
            if f in played:
                continue
            if not stable(f):
                continue          # 還在寫入，下一輪再處理
            played.add(f)
            play(f)
        # 記憶體防護：已播集合過大時，只保留最近 100 個檔名
        if len(played) > 500:
            recent = set(sorted(glob.glob(PATTERN))[-100:])
            played = recent
    except Exception as e:
        print(f"[jn1-tts-player] 迴圈錯誤：{e}", flush=True)
    time.sleep(POLL)
