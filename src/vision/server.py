"""robotcar-vision: moondream2 via transformers（GPU）

M11：不靠 ollama，用 transformers 直跑 moondream2
- 模型：vikhyatk/moondream2（官方）
- 推理：GPU PyTorch
- 記憶體：必要時停 qwen，一次一個大模型
"""
import os
import time
from fastapi import FastAPI, UploadFile, File
from PIL import Image
import io
import torch

app = FastAPI(title="robotcar-vision", version="3.0.0")

_moondream = None
MODEL_PATH = "/data/hf/moondream2"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def _load_moondream():
    """載入 moondream2（transformers API）"""
    global _moondream
    if _moondream is not None:
        return True
    
    try:
        print("[vision] Loading moondream2 from transformers...", flush=True)
        from transformers import AutoModelForCausalLM, AutoTokenizer
        
        # 檢查本地模型或線上拉取
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
        print("[vision] moondream2 loaded successfully!", flush=True)
        return True
    except Exception as e:
        print(f"[vision] Failed to load moondream2: {e}", flush=True)
        return False

@app.get("/health")
def health():
    """健康檢查"""
    if _load_moondream():
        return {"ok": True, "engine": "moondream2"}
    else:
        return {"ok": False, "engine": "moondream2", "error": "Model not loaded"}

@app.post("/capture")
async def capture(file: UploadFile = File(...), prompt: str = None):
    """從上傳的圖片生成描述"""
    
    if not _load_moondream():
        return {"ok": False, "error": "moondream2 not available"}
    
    try:
        # 讀取圖片
        img_data = await file.read()
        image = Image.open(io.BytesIO(img_data)).convert("RGB")
        
        # 預設提示
        if not prompt:
            prompt = "用中文詳細描述這個畫面。"
        
        print(f"[vision] Inferencing: {prompt}", flush=True)
        
        # moondream2 推論
        tokenizer = _moondream["tokenizer"]
        model = _moondream["model"]
        
        # 官方 API：encode_image + answer_question
        image_embeds = model.encode_image(image)
        answer = model.answer_question(
            image_embeds,
            prompt,
            tokenizer
        )
        
        return {"ok": True, "description": answer}
    except Exception as e:
        print(f"[vision] Inference failed: {e}", flush=True)
        return {"ok": False, "error": str(e)[:100]}

if __name__ == "__main__":
    import uvicorn
    print("[vision] Starting FastAPI server...", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
