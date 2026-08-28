"""robotcar-asr v3 — SenseVoice (sherpa-onnx) + Whisper fallback.

ASR_ENGINE=sensevoice (default): SenseVoice ONNX via sherpa-onnx (M8c).
    Chinese-first, zh/en code-switching, emotion+event tags, ITN; pure ONNX
    No PyTorch needed. Fast & accurate on CPU.
ASR_ENGINE=whisper: faster-whisper small as fallback.
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

app = FastAPI(title="robotcar-asr", version="3.0.0")
_model = None
_tag_re = re.compile(r"<\|[^|]*\|>")

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
            print(f"[asr] Loading SenseVoice via sherpa-onnx (M8c)...", flush=True)
            import sherpa_onnx
            
            # 模型路徑（預編譯模型）
            model_dir = "/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
            if not os.path.isdir(model_dir):
                print(f"[asr] Model directory not found: {model_dir}", flush=True)
                print(f"[asr] Falling back to Whisper", flush=True)
                ENGINE = "whisper"
                # 繼續 Whisper 加載...
                _load_whisper()
                return
            
            print(f"[asr] Initializing SenseVoice recognizer...", flush=True)
            recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=f"{model_dir}/model.int8.onnx",
                tokens=f"{model_dir}/tokens.txt",
                num_threads=2,
                use_itn=True,
                provider="cpu"  # 重要：用 CPU，不是 CUDA
            )
            print(f"[asr] SenseVoice loaded successfully!", flush=True)
            _model = ("sensevoice", recognizer)
            return
        except Exception as e:
            print(f"[asr] SenseVoice load failed: {e}", flush=True)
            print(f"[asr] Falling back to Whisper", flush=True)
            ENGINE = "whisper"


def _load_whisper():
    """Fallback to Whisper."""
    global _model
    from faster_whisper import WhisperModel
    device = os.environ.get("ASR_DEVICE", "auto")
    compute_type = os.environ.get("ASR_COMPUTE", "float16")
    
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    
    try:
        _model = ("whisper", WhisperModel(os.environ.get("WHISPER_MODEL", "small"),
                                          device=device, compute_type=compute_type))
    except Exception as e:
        print(f"[asr] Whisper with device={device} failed ({e}); fallback to CPU int8", flush=True)
        _model = ("whisper", WhisperModel(os.environ.get("WHISPER_MODEL", "small"),
                                          device="cpu", compute_type="int8"))


def _clean(text: str) -> str:
    return _tag_re.sub("", text or "").strip()


def _transcribe(path: str) -> str:
    _load()
    kind, m = _model
    
    if kind == "sensevoice":
        # SenseVoice 辨識流程
        try:
            import soundfile as sf
            # 讀取音頻文件
            audio, sample_rate = sf.read(path)
            
            # 如果採樣率不是 16kHz，轉換
            if sample_rate != 16000:
                import librosa
                audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
                sample_rate = 16000
            
            # 創建流並辨識
            stream = m.create_stream()
            stream.accept_waveform(sample_rate, audio)
            m.decode_stream(stream)
            result = m.get_result(stream)
            txt = result.text if hasattr(result, 'text') else str(result)
            return _apply_hotwords(_clean(txt))
        except Exception as e:
            print(f"[asr] SenseVoice transcription failed: {e}", flush=True)
            # Fallback to Whisper
            ENGINE = "whisper"
            _load()
            kind, m = _model
    
    # Whisper 路徑
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
