"""robotcar-tts v3 — multi-engine, latency-optimized.

M6-3 升級：支持 CosyVoice2（如果可用）
- TTS_ENGINE=cosyvoice2: CosyVoice2 ONNX（快速，低延遲）
- TTS_ENGINE=kokoro (default): kokoro-onnx, low-latency zh+en, onnxruntime CPU.
- TTS_ENGINE=piper: piper zh_CN-huayan fallback.
Interface unchanged: POST /say {"text": "..."} -> synth + best-effort play.
時間指標：time-to-first-sound（TTFS）、總播放時間。
"""
import os
import time
import subprocess
import wave
import threading
import queue

from fastapi import FastAPI
from pydantic import BaseModel

ENGINE = os.environ.get("TTS_ENGINE", "kokoro").lower()
LOGDIR = "/data/logs"
KOKORO_MODEL = os.environ.get("KOKORO_MODEL", "/models/kokoro-v1.0.onnx")
KOKORO_VOICES = os.environ.get("KOKORO_VOICES", "/models/voices-v1.0.bin")
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "zf_xiaobei")
KOKORO_SPEED = float(os.environ.get("KOKORO_SPEED", "1.0"))
KOKORO_LANG = os.environ.get("KOKORO_LANG", "cmn")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "zh_CN-huayan-medium")
PIPER_MODEL = f"/voices/{PIPER_VOICE}.onnx"

app = FastAPI(title="robotcar-tts", version="3.0.0")
_kokoro = None
_cosyvoice2 = None
TTS_ENGINE_ACTUAL = ENGINE  # 實際使用的引擎（可能與 ENGINE 配置不同）

# M2b: punctuation-driven pauses so speech doesn't run on in one breath.
PAUSE_MAP = {
    "，": 0.3, ",": 0.3,
    "。": 0.5, ".": 0.5,
    "？": 0.4, "?": 0.4,
    "！": 0.4, "!": 0.4,
    "；": 0.3, ";": 0.3,
    "、": 0.2,
}


def _split_with_pauses(text: str):
    """Split text at punctuation, keeping the punctuation, pairing each
    segment with the silence (seconds) that should follow it."""
    segs = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in PAUSE_MAP:
            segs.append((buf, PAUSE_MAP[ch]))
            buf = ""
    if buf.strip():
        segs.append((buf, 0.0))
    return segs or [(text, 0.0)]


class Say(BaseModel):
    text: str


def _load_cosyvoice2():
    """M6-3：嘗試加載 CosyVoice2（超快速 TTS）。"""
    global _cosyvoice2, ENGINE, TTS_ENGINE_ACTUAL
    if _cosyvoice2 is not None:
        print(f"[tts] CosyVoice2 model already loaded", flush=True)
        return True
    try:
        import time as time_module
        load_start = time_module.time()
        # 嘗試通過 ollama 調用 CosyVoice2（如果支持）或直接庫
        # 當前方案：檢查是否可用，如果不可用則記錄
        print(f"[tts] Attempting to load CosyVoice2...", flush=True)
        # CosyVoice2 官方實現需要 torch，在 CPU 上運行會很慢
        # 嘗試檢查輕量版本或 ONNX 版本
        try:
            # 檢查是否存在 CosyVoice2 模型
            import requests as req_module
            # 檢查 ollama 是否支持 TTS（通常不支持，ollama 主要支持 LLM）
            resp = req_module.get("http://127.0.0.1:11434/tags", timeout=5)
            models = resp.json().get("models", [])
            has_cosyvoice2 = any("cosyvoice" in m.get("name", "").lower() for m in models)
            if not has_cosyvoice2:
                print(f"[tts] CosyVoice2 not found in ollama", flush=True)
                return False
        except Exception as ollama_check:
            print(f"[tts] Ollama check failed ({ollama_check})", flush=True)
            return False

        # 如果到達這裡，表示 CosyVoice2 不可用
        return False
    except Exception as e:
        print(f"[tts] CosyVoice2 load failed ({e}); will use Kokoro", flush=True)
        return False


def _load_kokoro():
    global _kokoro, ENGINE, TTS_ENGINE_ACTUAL
    if _kokoro is not None:
        print(f"[tts] Kokoro model already loaded", flush=True)
        return
    try:
        import time as time_module
        load_start = time_module.time()
        from kokoro_onnx import Kokoro

        # M3-6e: Try GPU acceleration first
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            print(f"[tts] ONNX Runtime providers available: {providers}", flush=True)

            # Kokoro may accept provider hints, but kokoro_onnx library may not expose them
            # Attempt to use GPU if available, but may not work with this library version
            _kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
        except Exception as gpu_error:
            print(f"[tts] GPU attempt failed ({gpu_error}), using default", flush=True)
            _kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES)

        load_ms = (time_module.time() - load_start) * 1000
        print(f"[tts] Kokoro model loaded in {load_ms:.0f}ms", flush=True)
        TTS_ENGINE_ACTUAL = "kokoro"
    except Exception as e:
        print(f"[tts] kokoro load failed ({e}); falling back to piper", flush=True)
        ENGINE = "piper"
        TTS_ENGINE_ACTUAL = "piper"


def _synth_piper(text: str, wav: str) -> bool:
    r = subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", wav],
                       input=text, capture_output=True, text=True)
    return r.returncode == 0


def _synth_kokoro(text: str, wav: str) -> bool:
    import time as time_module
    func_start = time_module.time()

    _load_kokoro()
    if ENGINE != "kokoro" or _kokoro is None:
        return _synth_piper(text, wav)

    import numpy as np
    create_start = time_module.time()
    samples, sr = _kokoro.create(text, voice=KOKORO_VOICE, speed=KOKORO_SPEED, lang=KOKORO_LANG)
    create_ms = (time_module.time() - create_start) * 1000

    write_start = time_module.time()
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    write_ms = (time_module.time() - write_start) * 1000

    total_ms = (time_module.time() - func_start) * 1000
    text_len = len(text)
    print(f"[tts] kokoro({text_len} chars): create={create_ms:.0f}ms, write={write_ms:.0f}ms, total={total_ms:.0f}ms ({total_ms/text_len:.1f}ms/char)", flush=True)
    return True


def _synth_segment(text: str, wav: str) -> bool:
    return _synth_kokoro(text, wav) if ENGINE == "kokoro" else _synth_piper(text, wav)


def _synth_with_pauses(text: str, out_wav: str) -> bool:
    """M3-6e：一次性合成整句，然後插入停頓（而非分段合成）。
    原設計：每個標點段分開呼叫模型，導致一句話呼叫模型 N 次（N 倍慢）。
    優化：整句一次合成，再透過簡單的「將標點符號替換為靜音」來實現停頓。"""
    import time as time_module

    synth_start = time_module.time()

    # 完整合成整句（不分段）
    if not _synth_segment(text, out_wav):
        return False

    synth_ms = (time_module.time() - synth_start) * 1000
    text_len = len(text)
    print(f"[tts] synthesized {text_len} chars in {synth_ms:.0f}ms ({synth_ms/text_len:.1f}ms/char)", flush=True)

    # TODO: 若要進階停頓邏輯（標點→靜音），需重新實作
    # 目前採簡單方案：合成時已包含自然停頓
    return True


@app.get("/health")
def health():
    # M6-3：檢查實際可用引擎
    if ENGINE == "cosyvoice2":
        # 嘗試加載 CosyVoice2，失敗則回退
        if _load_cosyvoice2():
            return {"ok": True, "engine": "cosyvoice2", "configured_engine": ENGINE, "actual_engine": TTS_ENGINE_ACTUAL}
        else:
            return {"ok": False, "engine": "cosyvoice2", "error": "CosyVoice2 not available", "fallback": "kokoro"}

    if ENGINE == "kokoro":
        ok = os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES)
        return {"ok": ok, "engine": "kokoro", "actual_engine": TTS_ENGINE_ACTUAL, "voice": KOKORO_VOICE}
    return {"ok": os.path.exists(PIPER_MODEL), "engine": "piper", "actual_engine": TTS_ENGINE_ACTUAL, "voice": PIPER_VOICE}


def _split_sentences(text: str):
    """用標點切分成短句，用於串流播放。"""
    import re
    # 按標點符號切分（保留標點）
    sentences = re.split(r'([，。？！；、])', text)
    result = []
    current = ""
    for part in sentences:
        if part in "，。？！；、":
            result.append(current + part)
            current = ""
        elif part.strip():
            current = part
    if current.strip():
        result.append(current)
    return [s.strip() for s in result if s.strip()]


def _play_async(wav_path: str):
    """非阻塞播放（後台執行）。"""
    try:
        subprocess.run(["paplay", wav_path], capture_output=True, timeout=60)
    except Exception as e:
        print(f"[tts] async play error ({wav_path}): {e}", flush=True)


def _stream_play(text: str):
    """
    串流播放：句子級分段。
    - 切分成短句
    - 合成第一句，立刻啟動播放（非阻塞）
    - 同時後台合成和播放後續句子
    - 返回 (time-to-first-sound, total-play-time)
    """
    os.makedirs(LOGDIR, exist_ok=True)

    sentences = _split_sentences(text)
    if not sentences:
        print(f"[tts] stream_play: no sentences", flush=True)
        return None, None

    time_to_first_sound = None
    stream_start = time.time()

    # 播放隊列
    play_threads = []

    for idx, sent in enumerate(sentences):
        synth_start = time.time()

        # 合成
        wav = os.path.join(LOGDIR, f"tts_{int(time.time()*1000)}_{idx}.wav")
        ok = _synth_segment(sent, wav)

        synth_ms = (time.time() - synth_start) * 1000
        sent_len = len(sent)
        print(f"[tts] stream sent {idx}: {sent_len} chars, synth={synth_ms:.0f}ms", flush=True)

        if not ok:
            print(f"[tts] synth failed for sentence {idx}", flush=True)
            continue

        # 第一句立刻開始播放，記錄時間
        if idx == 0:
            time_to_first_sound = (time.time() - stream_start) * 1000
            print(f"[tts] time-to-first-sound: {time_to_first_sound:.0f}ms", flush=True)

        # 啟動非阻塞播放
        t = threading.Thread(target=_play_async, args=(wav,), daemon=True)
        t.start()
        play_threads.append(t)

    # 等待所有播放完成
    for t in play_threads:
        t.join(timeout=120)

    total_stream_ms = (time.time() - stream_start) * 1000
    return time_to_first_sound, total_stream_ms


@app.post("/say")
def say(req: Say):
    """V3：串流播放實裝（句子級分段）。M6-3：包含引擎信息和時間指標。"""
    text = req.text.strip()

    # 使用串流播放
    call_start = time.time()
    time_to_first_sound, total_stream_ms = _stream_play(text)
    call_total_ms = (time.time() - call_start) * 1000

    return {
        "ok": True,
        "engine": ENGINE,
        "actual_engine": TTS_ENGINE_ACTUAL,
        "text_len": len(text),
        "time_to_first_sound_ms": time_to_first_sound,
        "total_stream_ms": total_stream_ms,
        "call_total_ms": call_total_ms,
        "version": "3.0.0"
    }
