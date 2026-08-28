"""robotcar-vision: moondream2 via transformers（延遲載入·安全版）

M13：避免容器啟動時載入大模型，改為延遲加載或後台線程
- FastAPI 啟動立即返回 /health ok（服務先健康）
- 模型在後台執行緒加載（不阻塞容器）
- /describe 若模型未加載/失敗 → 誠實拒答
"""
import os
import threading
import time
from fastapi import FastAPI
from PIL import Image
import io
import torch
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="robotcar-vision", version="3.1.0")

_moondream = None
_loading = False
_load_error = None
MODEL_PATH = "/data/hf/moondream2"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def _load_moondream_bg():
    """後台執行緒載入 moondream2（非阻塞）"""
    global _moondream, _loading, _load_error

    if _moondream is not None:
        return

    _loading = True
    try:
        print("[vision] 後台開始載入 moondream2...", flush=True)
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            "vikhyatk/moondream2",
            trust_remote_code=True,
            cache_dir="/data/hf"
        )

        model = AutoModelForCausalLM.from_pretrained(
            "vikhyatk/moondream2",
            trust_remote_code=True,
            torch_dtype=torch.float16,
            device_map={"": DEVICE},
            cache_dir="/data/hf"
        )

        _moondream = {"tokenizer": tokenizer, "model": model}
        _load_error = None
        print("[vision] moondream2 後台載入完成！", flush=True)
    except Exception as e:
        _load_error = str(e)
        print(f"[vision] 後台載入失敗：{_load_error}", flush=True)
    finally:
        _loading = False

# 應用啟動時立即啟動後台載入（不阻塞 FastAPI）
@app.on_event("startup")
async def startup_event():
    """FastAPI 啟動事件：在後台執行緒載入模型"""
    print("[vision] FastAPI 已啟動，後台開始載入 moondream2...", flush=True)
    bg_thread = threading.Thread(target=_load_moondream_bg, daemon=True)
    bg_thread.start()

@app.get("/health")
def health():
    """健康檢查：立即返回 ok（不等模型）"""
    return {
        "ok": True,
        "engine": "moondream2",
        "model_loaded": _moondream is not None,
        "model_loading": _loading,
        "model_error": _load_error
    }

@app.post("/capture")
async def capture(prompt: str = None):
    """場景描述：延遲載入或失敗時誠實拒答"""

    # 若模型未加載，嘗試同步等待（最多 30 秒）
    if _moondream is None:
        if _load_error:
            # 已嘗試加載但失敗
            return {
                "ok": False,
                "source": "vlm-offline",
                "error": f"moondream2 模型加載失敗：{_load_error[:100]}"
            }

        # 正在加載，等待或拒答
        print("[vision] 等待模型加載...", flush=True)
        wait_start = time.time()
        while _moondream is None and _loading and (time.time() - wait_start) < 30:
            time.sleep(0.5)

        if _moondream is None:
            return {
                "ok": False,
                "source": "vlm-offline",
                "error": "moondream2 模型加載中或失敗，場景描述功能暫不可用"
            }

    try:
        # 讀取攝像頭
        import cv2
        cap = cv2.VideoCapture(0)
        ok, frame = cap.read()
        cap.release()

        if not ok or frame is None:
            return {"ok": False, "source": "vlm-offline", "error": "camera read failed"}

        # 轉換為 PIL Image
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        # 預設提示
        if not prompt:
            prompt = "用中文詳細描述這個畫面。"

        print(f"[vision] 推論中：{prompt}", flush=True)

        # moondream2 推論
        tokenizer = _moondream["tokenizer"]
        model = _moondream["model"]

        image_embeds = model.encode_image(image)
        answer = model.answer_question(
            image_embeds,
            prompt,
            tokenizer
        )

        return {
            "ok": True,
            "source": "vision-vlm",
            "description": answer
        }
    except Exception as e:
        print(f"[vision] 推論失敗：{e}", flush=True)
        return {
            "ok": False,
            "source": "vlm-offline",
            "error": str(e)[:100]
        }
