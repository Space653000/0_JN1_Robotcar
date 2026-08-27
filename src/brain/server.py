"""robotcar-brain v2 — orchestration spine.

Design (see docs/J4012_M2_SW_PLAN.md):
  * Capability Registry: each skill maps to a module URL + health. On-demand
    modules that are down degrade gracefully instead of crashing the reply.
  * Fast intent router (regex, zh/en) picks the cheapest path that answers:
      看到什麼/前面有什麼 -> perception /state   (instant, no big model)
      仔細描述/這是什麼     -> vision /capture     (VLM, on-demand)
      讀字/上面寫什麼       -> ocr /read           (PaddleOCR)
      多遠/距離/深度        -> depth /estimate      (monocular depth)
      其他                  -> LLM chat (with short memory)
  * Short conversational memory (~8 turns) shared across /ask and /talk.
  * M3-1c: Global Traditional Chinese output (simple+complex) via opencc (s2twp).
Backwards compatible with the M1 asr(/listen)+tts(/say) contract.
"""
import os
import re
from collections import deque

import requests
from fastapi import FastAPI
from pydantic import BaseModel
from opencc import OpenCC

OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama-new:11434")
LLM = os.environ.get("LLM_MODEL", "qwen2.5:3b")
NUM_CTX = int(os.environ.get("LLM_NUM_CTX", "2048"))
SECS = int(os.environ.get("LISTEN_SECONDS", "5"))
MEM_TURNS = int(os.environ.get("MEM_TURNS", "8"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "180"))

_cc = OpenCC("s2twp")

# YOLO 80 classes for hallucination detection
YOLO_CLASSES = {
    "person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa",
    "pottedplant", "bed", "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote",
    "keyboard", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
}

REGISTRY = {
    "asr":        {"url": os.environ.get("ASR_URL", "http://asr:8000"),       "on_demand": False},
    "tts":        {"url": os.environ.get("TTS_URL", "http://tts:8000"),       "on_demand": False},
    "perception": {"url": os.environ.get("PERCEPTION_URL", "http://perception:8000"), "on_demand": False},
    "vision":     {"url": os.environ.get("VISION_URL", "http://vision:8000"), "on_demand": True},
    "ocr":        {"url": os.environ.get("OCR_URL", "http://ocr:8000"),       "on_demand": True},
    "depth":      {"url": os.environ.get("DEPTH_URL", "http://depth:8000"),   "on_demand": True},
}

SYS = ("你是一台機器車上的語音助理。用繁體中文、口語、簡潔地回答;"
       "使用者可能中英文夾雜,你都聽得懂,但一律用繁體中文回覆。"
       "回答盡量在兩三句內,不要條列、不要客套。")

app = FastAPI(title="robotcar-brain", version="2.0.0")
_memory = deque(maxlen=MEM_TURNS * 2)

FAQ_PATTERNS = [
    ("faq_name",    r"你(叫|是)什麼(名字)?|你的名字(是什麼)?|你是誰"),
    ("faq_ability", r"你(會|能)(做)?什麼|你有什麼功能|你能幫我做什麼|你能做什麼"),
    ("faq_battery", r"電池|電量|還剩多少電|沒電"),
    ("faq_where",   r"你在(哪|哪裡|哪兒)|你現在的位置|你人在哪"),
]
FAQ_ANSWERS = {
    "faq_name":    "我是 JN1,你的機器人車語音助理。",
    "faq_ability": "我可以陪你聊天、幫你看看前面有什麼、讀文字、估計距離,以後還能自己開著到處跑。",
    "faq_battery": "電池感測器還沒接上,目前沒辦法回報實際電量喔。",
    "faq_where":   "我目前固定在測試工作站上,還沒裝上底盤跟定位系統。",
}

REFERENT_PATTERN = re.compile(r"那(個|是)?(東西)?(到底)?是什麼|那是啥|你剛(剛|才)說的是什麼|剛剛(說|提到)的是什麼")

INTENT_PATTERNS = [
    ("ocr",    r"(讀|唸|念).*(字|標|牌|文)|上面(寫|是).*(什麼|啥)|字幕|招牌|看板|菜單|OCR|文字內容"),
    ("depth",  r"多遠|多近|距離|離我|幾公尺|幾米|深度|前面.*(多遠|距離)"),
    ("state",  r"(看到|看見|前面|周圍|附近|旁邊|眼前|畫面裡?|鏡頭).*(什麼|啥|東西|人|物|幾個)|"
               r"有沒有(人|東西|貓|狗|車)|有幾(個|人)|數一?下|現在.*(看到|有什麼)"),
    ("describe", r"(仔細|詳細|好好).*(描述|說明|看)|這是(什麼|啥)|描述.*(畫面|場景|這)|"
                 r"畫面(是|裡有).*(什麼|啥)|看看這(個|張)|幫我看(一下)?這"),
]
FAQ_RE = [(name, re.compile(p)) for name, p in FAQ_PATTERNS]
INTENT_RE = [(name, re.compile(p)) for name, p in INTENT_PATTERNS]

# --- short-term entity memory (M2b: last_objects / last_location, for 代詞解析) ---
_LOCATION_RE = re.compile(r"我在(.{1,10}?)(,|，|。|$)")
_SIMPLE_NOUN_RE = re.compile(r"^[一-鿿]{1,6}$")
_GREETING_STOPWORDS = {
    "你好", "哈囉", "嗨", "喂", "早安", "午安", "晚安", "再見", "掰掰",
    "謝謝", "感謝", "好的", "好啊", "不客氣", "沒問題", "請問", "抱歉",
    "對不起", "不好意思", "拜託", "麻煩", "辛苦了",
}
_last_objects = deque(maxlen=5)
_last_location = {"value": None}


def to_traditional(text: str) -> str:
  """Convert simplified Chinese + mixed text to Traditional Chinese (Taiwan)."""
  if not text:
    return text
  return _cc.convert(text)


def remember_entities(text: str, matched_intent: str):
    """Update last_objects / last_location from plain user utterances."""
    t = (text or "").strip()
    if not t:
        return
    loc = _LOCATION_RE.search(t)
    if loc:
        _last_location["value"] = loc.group(1)
    # A bare short noun-like utterance ("杯子") with no other intent match is
    # treated as the user pointing something out -> remember it as an object.
    # Common greetings/fillers are excluded so they don't pollute the memory.
    if matched_intent == "chat" and _SIMPLE_NOUN_RE.match(t) and t not in _GREETING_STOPWORDS:
        if not _last_objects or _last_objects[-1] != t:
            _last_objects.append(t)


def remember_objects_from_state(state: dict):
    dets = state.get("objects") or state.get("detections") or []
    seen = set()
    for d in dets:
        lbl = d.get("label_zh") or d.get("label") or d.get("name")
        if lbl and lbl not in seen:
            seen.add(lbl)
            if not _last_objects or _last_objects[-1] != lbl:
                _last_objects.append(lbl)


def route(text: str) -> str:
    t = (text or "").strip()
    for name, rx in FAQ_RE:
        if rx.search(t):
            return name
    if REFERENT_PATTERN.search(t):
        return "referent"
    for name, rx in INTENT_RE:
        if rx.search(t):
            return name
    return "chat"


def _up(name: str) -> bool:
    m = REGISTRY.get(name)
    if not m:
        return False
    try:
        return requests.get(f"{m['url']}/health", timeout=5).status_code == 200
    except Exception:
        return False


def _chat(user: str, system: str = SYS, remember: bool = True) -> str:
    msgs = [{"role": "system", "content": system}]
    msgs.extend(_memory)
    msgs.append({"role": "user", "content": user})
    r = requests.post(f"{OLLAMA}/api/chat",
                      json={"model": LLM, "stream": False, "messages": msgs,
                            "options": {"num_ctx": NUM_CTX}},
                      timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    out = r.json()["message"]["content"].strip()
    if remember:
        _memory.append({"role": "user", "content": user})
        _memory.append({"role": "assistant", "content": out})
    return out


def _speak(text: str):
    try:
        text_trad = to_traditional(text)
        return requests.post(f"{REGISTRY['tts']['url']}/say",
                             json={"text": text_trad}, timeout=120).json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _perception_state():
    r = requests.post(f"{REGISTRY['perception']['url']}/state", timeout=10)
    r.raise_for_status()
    return r.json()


def _vlm_capture(prompt=None):
    try:
        payload = {"prompt": prompt} if prompt else {}
        r = requests.post(f"{REGISTRY['vision']['url']}/capture", params=payload, timeout=200)
        data = r.json()
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error", "unknown error")}
        return data
    except requests.Timeout:
        return {"ok": False, "error": "vision timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


def _translate_vlm_to_zh(english_desc: str) -> str:
    """Translate English VLM description to Traditional Chinese via qwen2.5:3b.
    Uses explicit prompt to ensure Taiwan Traditional Chinese output."""
    try:
        prompt = f"翻譯成繁體中文（台灣用語），一句自然的話，不要清單。英文：{english_desc}"
        r = requests.post(f"{OLLAMA}/api/chat",
                          json={"model": LLM, "stream": False,
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        zh_desc = r.json()["message"]["content"].strip()
        return to_traditional(zh_desc)
    except Exception as e:
        return f"[翻譯失敗: {str(e)[:30]}]"


def _ocr_read():
    r = requests.post(f"{REGISTRY['ocr']['url']}/read", timeout=120)
    r.raise_for_status()
    return r.json()


def _depth_estimate():
    r = requests.post(f"{REGISTRY['depth']['url']}/estimate", timeout=120)
    r.raise_for_status()
    return r.json()


def _fmt_state_zh(state: dict) -> str:
    dets = state.get("objects") or state.get("detections") or []
    if not dets:
        return "目前畫面裡沒有偵測到明顯的物體。"
    counts = {}
    for d in dets:
        lbl = d.get("label_zh") or d.get("label") or d.get("name") or "物體"
        counts[lbl] = counts.get(lbl, 0) + 1
    parts = [f"{n}個{lbl}" if n > 1 else lbl for lbl, n in counts.items()]
    return "我看到 " + "、".join(parts) + "。"


def _verify_no_hallucination(natural_desc: str, detected_labels_zh: set) -> tuple:
    """驗證自然句子是否出現了清單沒有的物體（防幻覺檢查）。

    Args:
        natural_desc: 生成的自然句子
        detected_labels_zh: 實際偵測到的物體名稱（繁體中文）

    Returns:
        (is_clean, hallucinated_objects): 是否無幻覺 + 幻覺物體列表
    """
    hallucinated = []

    # 構建 YOLO 類名的繁體版本映射（簡單版）
    yolo_zh_map = {
        "人": "person", "瓶子": "bottle", "椅子": "chair", "桌子": "diningtable",
        "車": "car", "狗": "dog", "貓": "cat", "馬": "horse", "牛": "cow",
        "杯子": "cup", "叉": "fork", "刀": "knife", "湯匙": "spoon", "碗": "bowl",
        "香蕉": "banana", "蘋果": "apple", "三明治": "sandwich", "橙": "orange",
        "電腦": "laptop", "鼠標": "mouse", "遙控器": "remote", "鍵盤": "keyboard",
        "微波爐": "microwave", "烤箱": "oven", "冰箱": "refrigerator", "書": "book",
        "時鐘": "clock", "花瓶": "vase", "剪刀": "scissors", "熊": "teddy bear"
    }

    # 檢查句子中是否出現了 YOLO 類中的物體名（但不在偵測清單中）
    for yolo_zh, yolo_en in yolo_zh_map.items():
        if yolo_zh in natural_desc and yolo_zh not in detected_labels_zh:
            hallucinated.append(yolo_zh)

    is_clean = len(hallucinated) == 0
    return is_clean, hallucinated


def _get_position_and_distance(bbox, image_width=640, image_height=480):
    """從 bbox 推斷位置（左/正前方/右）和距離（近/遠）。

    Returns: (position, distance) 如 ("正前方", "近")
    """
    if not bbox or len(bbox) < 4:
        return "正前方", "中距"

    x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
    x_mid = (x1 + x2) / 2
    y_mid = (y1 + y2) / 2
    width = x2 - x1
    height = y2 - y1

    # 水平位置：左三分之一 / 中間 / 右三分之一
    if x_mid < image_width / 3:
        position = "左邊"
    elif x_mid > image_width * 2 / 3:
        position = "右邊"
    else:
        position = "正前方"

    # 距離：根據物體在畫面中的佔比
    # bbox 面積越大 → 物體離相機越近
    bbox_area = width * height
    frame_area = image_width * image_height
    ratio = bbox_area / frame_area

    if ratio > 0.25:  # 佔比 > 25%
        distance = "非常近"
    elif ratio > 0.15:  # 佔比 > 15%
        distance = "很近"
    elif ratio > 0.08:  # 佔比 > 8%
        distance = "近"
    elif ratio > 0.04:  # 佔比 > 4%
        distance = "中距"
    else:
        distance = "遠"

    return position, distance


def _describe_detections_naturally(dets: list) -> dict:
    """用 qwen2.5 生成自然句子描述偵測物體（嚴格限定只用清單物體）。
    M3-4b 升級：使用位置+距離+量詞讓句子更自然。

    Returns:
        {
            "reply": "自然句子",
            "is_clean": True/False (無幻覺),
            "hallucinated": ["物體1", "物體2"] (如果有幻覺)
        }
    """
    if not dets:
        return {
            "reply": "我前面沒看到明確的東西。",
            "is_clean": True,
            "hallucinated": []
        }

    # 构建物体清单，包含位置和距离信息
    obj_descriptions = []
    detected_labels_zh = set()
    for d in dets:
        lbl = d.get("label_zh") or d.get("label") or "物體"
        detected_labels_zh.add(lbl)
        bbox = d.get("bbox", [])

        # 推斷位置和距离
        position, distance = _get_position_and_distance(bbox)

        # 根據物體類型選擇量詞
        if lbl in ["人", "狗", "貓", "馬", "牛"]:
            quantifier = "一個"
        elif lbl in ["桌子", "椅子", "床", "沙發", "冰箱", "微波爐", "電視", "電腦"]:
            quantifier = "一台" if lbl == "電視" or lbl == "電腦" else "一個"
        elif lbl in ["瓶子", "杯子", "碗", "盤子"]:
            quantifier = "一個"
        else:
            quantifier = "一個"

        obj_descriptions.append({
            "label": lbl,
            "position": position,
            "distance": distance,
            "quantifier": quantifier,
            "desc": f"{lbl}（{quantifier}，位置：{position}，距離：{distance}）"
        })

    # 构建详细的 prompt，要求更自然的语言
    obj_str = "、".join([o["desc"] for o in obj_descriptions])

    prompt = f"""你是機器人的眼睛。相機真實偵測到：{obj_str}。

用自然口語繁體中文一句話講你看到什麼，像跟朋友聊天一樣自然。用量詞（一個人、一台電視）、講出位置（正前方、左邊、右邊）和大概距離感。

嚴格規則：
1. 只能講清單裡的物體
2. 絕對不能加任何清單沒有的東西
3. 多個物體要通順組合（例：「我看到一個人在正前方，右邊還有一個瓶子」）
4. 清單空就說「我前面沒看到明確的東西」
5. 不要說「YOLO偵測」或「邊界框」這類技術詞彙

生成的自然句子："""

    try:
        # 调用 LLM
        resp = requests.post(
            f"{OLLAMA}/api/chat",
            json={
                "model": LLM,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"num_ctx": NUM_CTX}
            },
            timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        natural_desc = resp.json()["message"]["content"].strip()

        # 转换为繁体
        natural_desc = _cc.convert(natural_desc)

        # 防幻觉验证
        is_clean, hallucinated = _verify_no_hallucination(natural_desc, detected_labels_zh)

        return {
            "reply": natural_desc,
            "is_clean": is_clean,
            "hallucinated": hallucinated
        }
    except Exception as e:
        # M3-4c：記錄真正的錯誤，便於診斷
        logger.error(f"自然句生成失敗（_describe_detections_naturally）: {type(e).__name__}: {str(e)}")
        # 失败时降级为原始格式
        return {
            "reply": _fmt_state_zh({"detections": dets}),
            "is_clean": True,
            "hallucinated": [],
            "_error": f"{type(e).__name__}: {str(e)[:100]}"  # 除錯用，外部可見
        }


def handle_intent(intent: str, text: str) -> dict:
    try:
        result = None
        if intent in FAQ_ANSWERS:
            result = {"reply": FAQ_ANSWERS[intent], "source": "faq"}
        elif intent == "referent":
            if _last_objects:
                result = {"reply": f"你剛剛提到的是「{_last_objects[-1]}」。",
                        "source": "memory", "last_objects": list(_last_objects)}
            else:
                result = {"reply": "我們剛剛好像沒有提到什麼特定的東西耶,可以再說一次嗎?",
                    "source": "memory"}
        elif intent == "state":
            if _up("perception"):
                st = _perception_state()
                remember_objects_from_state(st)
                # M3-4：用 qwen 生成自然句子描述偵測物體
                dets = st.get("detections") or []
                natural_data = _describe_detections_naturally(dets)
                result = {
                    "reply": natural_data["reply"],
                    "source": "perception-natural",
                    "state": st,
                    "hallucination_check": {
                        "is_clean": natural_data["is_clean"],
                        "hallucinated_objects": natural_data["hallucinated"]
                    }
                }
            else:
                result = {"reply": "視覺服務還沒啟動，我暫時看不到。", "source": "none"}
        elif intent == "describe":
            if _up("vision"):
                vlm_data = _vlm_capture("Describe this scene in detail, including objects, layout, lighting, and atmosphere. One sentence.")
                if vlm_data.get("ok"):
                    en_desc = vlm_data.get("description", "")
                    zh_desc = _translate_vlm_to_zh(en_desc)
                    result = {"reply": zh_desc, "source": "vision-translated", "vlm_en": en_desc}
                else:
                    result = {"reply": "相機或視覺服務有問題。", "source": "vision-error"}
            else:
                result = {"reply": "視覺服務還沒啟動。", "source": "none"}
        elif intent == "ocr":
            if _up("ocr"):
                o = _ocr_read()
                txt = o.get("text", "").strip()
                if not txt:
                    result = {"reply": "我沒讀到清楚的文字。", "source": "ocr"}
                else:
                    result = {"reply": "上面寫的是:" + to_traditional(txt), "source": "ocr", "ocr": o}
            else:
                result = {"reply": "文字辨識服務還沒啟動。", "source": "none"}
        elif intent == "depth":
            if _up("depth"):
                d = _depth_estimate()
                summary = d.get("summary_zh", "我估了一下前方的相對距離。")
                result = {"reply": to_traditional(summary),
                        "source": "depth", "depth": d}
            else:
                result = {"reply": "深度估計服務還沒啟動。", "source": "none"}
        else:
            llm_reply = _chat(text)
            result = {"reply": to_traditional(llm_reply), "source": "llm"}
        return result
    except Exception as e:
        return {"reply": "剛剛處理時出了點問題。", "source": "error", "error": str(e)}


class Ask(BaseModel):
    text: str
    speak: bool = True


@app.get("/health")
def health():
    st = {"ollama": False}
    try:
        st["ollama"] = requests.get(f"{OLLAMA}/api/tags", timeout=5).status_code == 200
    except Exception:
        st["ollama"] = False
    for name in REGISTRY:
        st[name] = _up(name)
    core = st["ollama"] and st["asr"] and st["tts"]
    return {"ok": core, "services": st, "llm": LLM, "mem_turns": MEM_TURNS}


@app.post("/ask")
def ask(req: Ask):
    intent = route(req.text)
    remember_entities(req.text, intent)
    res = handle_intent(intent, req.text)
    tts = _speak(res["reply"]) if req.speak else None
    return {"ok": True, "intent": intent, **res, "tts": tts}


@app.post("/talk")
def talk(seconds: int = 0):
    n = seconds or SECS
    try:
        a = requests.post(f"{REGISTRY['asr']['url']}/listen",
                          params={"seconds": n}, timeout=n + 90).json()
    except Exception as e:
        return {"ok": False, "stage": "asr", "error": str(e)}
    if not a.get("ok") or not a.get("text"):
        return {"ok": False, "stage": "asr", "detail": a}
    heard = a["text"]
    intent = route(heard)
    remember_entities(heard, intent)
    res = handle_intent(intent, heard)
    return {"ok": True, "heard": heard, "intent": intent, **res, "tts": _speak(res["reply"])}


@app.post("/see")
def see():
    # Direct vision capture with translation for /see endpoint
    if _up("vision"):
        vlm_data = _vlm_capture("Describe this scene in one sentence, list main objects.")
        if vlm_data.get("ok"):
            en_desc = vlm_data.get("description", "")
            zh_desc = _translate_vlm_to_zh(en_desc)
            res = {"ok": True, "reply": zh_desc, "source": "vision-translated", "vlm_en": en_desc, "intent": "describe"}
            return {"ok": True, **res, "tts": _speak(res["reply"])}
    return {"ok": False, "reply": "視覺服務不可用。", "source": "none", "tts": None}


@app.post("/reset")
def reset():
    _memory.clear()
    _last_objects.clear()
    _last_location["value"] = None
    return {"ok": True, "cleared": True}
