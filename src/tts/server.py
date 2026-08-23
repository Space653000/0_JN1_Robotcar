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
        return
    try:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    except Exception as e:
        print(f"[tts] kokoro load failed ({e}); falling back to piper", flush=True)
        ENGINE = "piper"


def _synth_piper(text: str, wav: str) -> bool:
    r = subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", wav],
                       input=text, capture_output=True, text=True)
    return r.returncode == 0


def _synth_kokoro(text: str, wav: str) -> bool:
    _load_kokoro()
    if ENGINE != "kokoro" or _kokoro is None:
        return _synth_piper(text, wav)
    import numpy as np
    samples, sr = _kokoro.create(text, voice=KOKORO_VOICE, speed=KOKORO_SPEED, lang=KOKORO_LANG)
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return True


def _synth_segment(text: str, wav: str) -> bool:
    return _synth_kokoro(text, wav) if ENGINE == "kokoro" else _synth_piper(text, wav)


def _synth_with_pauses(text: str, out_wav: str) -> bool:
    """Synthesize each punctuation-delimited segment separately, then splice
    them back together with silence for the natural pause."""
    segments = _split_with_pauses(text)
    frames = []
    params = None
    for i, (seg_text, pause) in enumerate(segments):
        seg_stripped = seg_text.strip()
        if not seg_stripped:
            continue
        part = f"{out_wav}.part{i}.wav"
        if not _synth_segment(seg_stripped, part):
            return False
        try:
            with wave.open(part, "rb") as w:
                if params is None:
                    params = w.getparams()
                frames.append(w.readframes(w.getnframes()))
        finally:
            try:
                os.unlink(part)
            except OSError:
                pass
        if pause > 0 and params is not None:
            n_frames = int(params.framerate * pause)
            silence = b"\x00" * (n_frames * params.sampwidth * params.nchannels)
            frames.append(silence)
    if not frames or params is None:
        return False
    with wave.open(out_wav, "wb") as w:
        w.setparams(params)
        for fr in frames:
            w.writeframes(fr)
    return True


@app.get("/health")
def health():
    if ENGINE == "kokoro":
        ok = os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICES)
        return {"ok": ok, "engine": "kokoro", "voice": KOKORO_VOICE}
    return {"ok": os.path.exists(PIPER_MODEL), "engine": "piper", "voice": PIPER_VOICE}


@app.post("/say")
def say(req: Say):
    os.makedirs(LOGDIR, exist_ok=True)
    wav = os.path.join(LOGDIR, f"tts_{int(time.time()*1000)}.wav")
    try:
        ok = _synth_with_pauses(req.text, wav)
    except Exception as e:
        return {"ok": False, "error": "synth failed", "detail": str(e)}
    if not ok:
        return {"ok": False, "error": "synth failed"}
    played, perr = False, ""
    try:
        pr = subprocess.run(["paplay", wav], capture_output=True, text=True, timeout=60)
        played = (pr.returncode == 0)
        perr = pr.stderr[-300:]
    except Exception as e:
        perr = str(e)
    return {"ok": True, "wav": wav, "engine": ENGINE, "played": played, "play_error": perr}
