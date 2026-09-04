#!/usr/bin/env python3
# jn1_tts_player.py — 在 J4012 主機上，把 TTS 產生的語音播到你插在機器上的耳機。
#
# 為什麼需要它：
#   TTS 服務跑在 Docker 容器裡，容器碰不到主機的 PulseAudio（容器內 paplay 會
#   回 "Access denied"）。但容器會把合成好的 wav 寫到共用資料夾 data/logs，
#   而主機以 jetson 身分跑 paplay 是可以正常出聲的。
#   所以這支在「主機、jetson 使用者、有音效工作階段」的環境跑，監看那個資料夾，
#   一有新語音就由主機播放 → 傳到你插在 J4012 上的耳機。
#
# 額外功能：語速調整（變速不變調）。不管容器用哪個引擎，都在這裡統一調速。
#
# 用法：
#   JN1_TTS_TEMPO=1.5 nohup python3 jn1_tts_player.py > /tmp/jn1_tts_player.log 2>&1 &
# 環境變數（都可不填）：
#   JN1_TTS_LOGDIR  預設 ~/0_JN1_Robotcar/data/logs
#   JN1_TTS_SINK    指定音效輸出裝置名稱；留空=系統預設（你的耳機）
#   JN1_TTS_POLL    掃描間隔秒數，預設 0.25
#   JN1_TTS_TEMPO   語速倍率，預設 1.0；1.5 = 快 1.5 倍（變速不變調）

import os, time, glob, subprocess, shutil, tempfile

LOGDIR  = os.environ.get("JN1_TTS_LOGDIR", os.path.expanduser("~/0_JN1_Robotcar/data/logs"))
POLL    = float(os.environ.get("JN1_TTS_POLL", "0.25"))
SINK    = os.environ.get("JN1_TTS_SINK", "").strip()
TEMPO   = float(os.environ.get("JN1_TTS_TEMPO", "1.0"))
PATTERN = os.path.join(LOGDIR, "tts_*.wav")

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
HAVE_SOX    = shutil.which("sox") is not None
DO_TEMPO    = abs(TEMPO - 1.0) > 0.01

played = set()
# 啟動時把「現有的」舊語音檔標記成已處理，避免一開機把歷史語音全部重播一遍。
for f in glob.glob(PATTERN):
    played.add(f)
print(f"[jn1-tts-player] 監看 {PATTERN}；啟動時既有 {len(played)} 檔（略過不播）", flush=True)
if SINK:
    print(f"[jn1-tts-player] 指定輸出裝置：{SINK}", flush=True)
if DO_TEMPO:
    tool = "ffmpeg" if HAVE_FFMPEG else ("sox" if HAVE_SOX else "無(需安裝 ffmpeg 或 sox)")
    print(f"[jn1-tts-player] 語速 x{TEMPO}（變速工具：{tool}）", flush=True)


def stable(path):
    """確認檔案已寫完：兩次取檔案大小一致、且大於 WAV 標頭(44 bytes)。"""
    try:
        s1 = os.path.getsize(path)
        time.sleep(POLL)
        s2 = os.path.getsize(path)
    except OSError:
        return False
    return s1 == s2 and s2 > 44


def retempo(path):
    """回傳調速後的暫存 wav 路徑；失敗或不需調速時回傳 None（用原檔）。"""
    if not DO_TEMPO:
        return None
    tmp = tempfile.NamedTemporaryFile(prefix="jn1tts_", suffix=".wav", delete=False).name
    try:
        if HAVE_FFMPEG:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
                 "-filter:a", f"atempo={TEMPO}", tmp],
                capture_output=True, text=True, timeout=60)
        elif HAVE_SOX:
            r = subprocess.run(["sox", path, tmp, "tempo", str(TEMPO)],
                               capture_output=True, text=True, timeout=60)
        else:
            os.remove(tmp)
            return None
        if r.returncode == 0 and os.path.getsize(tmp) > 44:
            return tmp
        print(f"[jn1-tts-player] 調速失敗，改播原速：{r.stderr.strip()[:120]}", flush=True)
    except Exception as e:
        print(f"[jn1-tts-player] 調速例外，改播原速：{e}", flush=True)
    if os.path.exists(tmp):
        os.remove(tmp)
    return None


def play(path):
    tmp = retempo(path)
    src = tmp or path
    cmd = ["paplay"] + (["--device", SINK] if SINK else []) + [src]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            spd = f" x{TEMPO}" if DO_TEMPO else ""
            print(f"[jn1-tts-player] ▶ 播放 {os.path.basename(path)}{spd}", flush=True)
        else:
            print(f"[jn1-tts-player] ✗ {os.path.basename(path)} rc={r.returncode} "
                  f"{r.stderr.strip()}", flush=True)
    except Exception as e:
        print(f"[jn1-tts-player] ✗ {os.path.basename(path)} {e}", flush=True)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


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
            played = set(sorted(glob.glob(PATTERN))[-100:])
    except Exception as e:
        print(f"[jn1-tts-player] 迴圈錯誤：{e}", flush=True)
    time.sleep(POLL)
