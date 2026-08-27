"""
M3-5a 工具路由層：輕量代理大腦

定義工具清單 + 路由邏輯
"""

TOOLS = {
    "look": {
        "url": "http://perception:8000/state",
        "method": "POST",
        "description": "前面有什麼（YOLO 偵測）"
    },
    "read": {
        "url": "http://ocr:8000/read",
        "method": "POST",
        "description": "唸字/讀文字（OCR）"
    },
    "recall": {
        "description": "記憶我們的對話歷史"
    },
    "chat": {
        "description": "一般聊天"
    }
}

def route_by_keywords(text: str) -> str:
    """用關鍵字做快速路由（備選方案）"""
    if any(w in text for w in ["前面", "看到", "有什麼", "有沒有", "偵測", "周圍"]):
        return "look"
    elif any(w in text for w in ["讀", "唸", "念", "字", "文字", "上面寫", "看板"]):
        return "read"
    elif any(w in text for w in ["我剛", "我說", "我叫", "我的名字", "記得"]):
        return "recall"
    else:
        return "chat"

def call_tool_look(requests_lib) -> dict:
    """呼叫 perception /state"""
    try:
        r = requests_lib.post("http://perception:8000/state", timeout=10)
        data = r.json()
        dets = data.get("detections", [])
        if dets:
            labels = [d.get("label_zh", d.get("label")) for d in dets]
            return {"ok": True, "data": labels, "raw": data}
        else:
            return {"ok": True, "data": [], "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def call_tool_read(requests_lib) -> dict:
    """呼叫 ocr /read"""
    try:
        r = requests_lib.post("http://ocr:8000/read", timeout=120)
        data = r.json()
        text = data.get("text", "").strip()
        return {"ok": True, "data": text, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}
