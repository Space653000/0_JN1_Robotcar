"""robotcar-asr v2 — dual-engine, memory-lean (no torch in the always-on path).

ASR_ENGINE=sensevoice (default): FunASR SenseVoice-Small ONNX via funasr_onnx.
    Chinese-first, zh/en code-switching, emotion+event tags, ITN; onnxruntime
    CPU only -> no torch (protects the always-on budget, M2_PLAN §C).
ASR_ENGINE=whisper: faster-whisper small (M1 baseline) as safe fallback.
Interface unchanged: POST /listen?seconds=N , POST /transcribe (file).
"""
import os
import re
import subprocess
import tempfile

from fastapi import FastAPI, UploadFile, File

ENGINE = os.environ.get("ASR_ENGINE", "sensevoice").lower()
LANG = os.environ.get("ASR_LANG", "auto")
SOURCE = os.environ.get("PULSE_SOURCE", "default")
HOTWORDS = [w for w in os.environ.get("ASR_HOTWORDS", "").split(",") if w.strip()]

app = FastAPI(title="robotcar-asr", version="2.0.0")
_model = None
_tag_re = re.compile(r"<\|[^|]*\|>")

# M2b: hotword post-correction — SenseVoice has no hotword-bias API and even
# faster-whisper's `hotwords` hint doesn't always land, so fix the common
# ASR mis-hearings of our own product names after transcription.
HOTWORD_FIXES = [
    (re.compile(r"(je[iy]\s?en\s?1|jn\s?一|杰n1|傑n1|jn幺|机n1|界n1)", re.IGNORECASE), "JN1"),
    (re.compile(r"(口可羅|口哥羅|扣扣羅|柯珂羅|可可羅|口可蘿|摳摳蘿)"), "Kokoro"),
    (re.compile(r"(傑森|杰特森|傑特森|節森|捷森|jetson)", re.IGNORECASE), "Jetson"),
]


def _apply_hotwords(text: str) -> str:
    for rx, repl in HOTWORD_FIXES:
        text = rx.sub(repl, text)
    return text


def _load():
    global _model, ENGINE
    if _model is not None:
        return
    if ENGINE == "sensevoice":
        try:
            from funasr_onnx import SenseVoiceSmall
            model_dir = os.environ.get("SENSEVOICE_DIR", "iic/SenseVoiceSmall")
            if not os.path.isdir(model_dir):
                from modelscope import snapshot_download
                model_dir = snapshot_download(model_dir)
            _model = ("sensevoice", SenseVoiceSmall(model_dir, batch_size=1, quantize=True))
            return
        except Exception as e:
            print(f"[asr] SenseVoice load failed ({e}); falling back to whisper", flush=True)
            ENGINE = "whisper"
    from faster_whisper import WhisperModel
    _model = ("whisper", WhisperModel(os.environ.get("WHISPER_MODEL", "small"),
                                      device="cpu", compute_type="int8"))


def _clean(text: str) -> str:
    return _tag_re.sub("", text or "").strip()


def _transcribe(path: str) -> str:
    _load()
    kind, m = _model
    if kind == "sensevoice":
        res = m(path, language=LANG, use_itn=True)
        item = res[0] if isinstance(res, (list, tuple)) and res else res
        txt = item["text"] if isinstance(item, dict) else str(item)
        return _apply_hotwords(_clean(txt))
    lang = None if LANG == "auto" else LANG
    segments, _info = m.transcribe(path, language=lang, vad_filter=True,
                                   hotwords=" ".join(HOTWORDS) or None)
    return _apply_hotwords("".join(s.text for s in segments).strip())


@app.get("/health")
def health():
    try:
        _load()
        return {"ok": True, "engine": _model[0], "lang": LANG, "hotwords": HOTWORDS}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/listen")
def listen(seconds: int = 5):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    cmd = ["ffmpeg", "-y", "-f", "pulse", "-i", SOURCE,
           "-t", str(seconds), "-ar", "16000", "-ac", "1", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"ok": False, "error": "record failed", "detail": r.stderr[-500:]}
    try:
        text = _transcribe(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return {"ok": True, "text": text}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(await file.read())
        path = f.name
    try:
        text = _transcribe(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return {"ok": True, "text": text}
