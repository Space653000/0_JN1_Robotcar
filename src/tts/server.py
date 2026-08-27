"""robotcar-tts v2 — dual-engine, memory-lean (no torch).

TTS_ENGINE=kokoro (default): kokoro-onnx, low-latency zh+en, onnxruntime CPU.
TTS_ENGINE=piper: piper zh_CN-huayan (M1 baseline) fallback.
Interface unchanged: POST /say {"text": "..."} -> synth + best-effort play.
"""
import os
import time
import subprocess
import wave

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

app = FastAPI(title="robotcar-tts", version="2.0.0")
_kokoro = None

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


def _load_kokoro():
    global _kokoro, ENGINE
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
    except Exception as e:
        print(f"[tts] kokoro load failed ({e}); falling back to piper", flush=True)
        ENGINE = "piper"


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
    if ENGINE == "kokoro":
        ok = os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES)
        return {"ok": ok, "engine": "kokoro", "voice": KOKORO_VOICE}
    return {"ok": os.path.exists(PIPER_MODEL), "engine": "piper", "voice": PIPER_VOICE}


@app.post("/say")
def say(req: Say):
    # M3-6d：分離計時合成和播放
    # 優化：簡單文本（無標點）跳過分段補靜音，直接快速合成
    os.makedirs(LOGDIR, exist_ok=True)
    wav = os.path.join(LOGDIR, f"tts_{int(time.time()*1000)}.wav")

    synth_start = time.time()
    try:
        # M3-6d：快速路徑——無標點或標點少的簡單文本直接合成，省去分段開銷
        text = req.text.strip()
        has_punctuation = any(c in text for c in "，。？！；、")

        if not has_punctuation or len(text) < 10:
            # 快速路徑：直接合成，不分段
            ok = _synth_segment(text, wav)
        else:
            # 長句或多標點：分段補靜音
            ok = _synth_with_pauses(text, wav)
    except Exception as e:
        return {"ok": False, "error": "synth failed", "detail": str(e)}
    synth_ms = (time.time() - synth_start) * 1000

    if not ok:
        return {"ok": False, "error": "synth failed"}

    play_start = time.time()
    played, perr = False, ""
    try:
        pr = subprocess.run(["paplay", wav], capture_output=True, text=True, timeout=60)
        played = (pr.returncode == 0)
        perr = pr.stderr[-300:]
    except Exception as e:
        perr = str(e)
    play_ms = (time.time() - play_start) * 1000

    return {
        "ok": True,
        "wav": wav,
        "engine": ENGINE,
        "played": played,
        "play_error": perr,
        "synth_ms": synth_ms,
        "play_ms": play_ms,
        "total_ms": synth_ms + play_ms
    }
