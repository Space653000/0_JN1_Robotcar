# M37 本地 qwen 確認  Sat Aug 29 12:43:19 AM UTC 2026

## 1) 直接 ollama 推理(本地主腦真活?)
[?2026h[?25l[1G⠙ [K[?25h[?2026l[?2026h[?25l[1G⠙ [K[?25h[?2026l[?2026h[?25l[1G⠹ [K[?25h[?2026l[?2026h[?25l[1G⠸ [K[?25h[?2026l[?2026h[?25l[1G⠼ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠧ [K[?25h[?2026l[?2026h[?25l[1G⠧ [K[?25h[?2026l[?2026h[?25l[1G⠇ [K[?25h[?2026l[?2026h[?25l[1G⠏ [K[?25h[?2026l[?2026h[?25l[1G⠋ [K[?25h[?2026l[?2026h[?25l[1G⠙ [K[?25h[?2026l[?2026h[?25l[1G⠸ [K[?25h[?2026l[?2026h[?25l[1G⠸ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠧ [K[?25h[?2026l[?2026h[?25l[1G⠧ [K[?25h[?2026l[?2026h[?25l[1G⠇ [K[?25h[?2026l[?2026h[?25l[1G⠏ [K[?25h[?2026l[?2026h[?25l[1G⠋ [K[?25h[?2026l[?2026h[?25l[1G⠙ [K[?25h[?2026l[?2026h[?25l[1G⠹ [K[?25h[?2026l[?2026h[?25l[1G⠸ [K[?25h[?2026l[?2026h[?25l[1G⠼ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠦ [K[?25h[?2026l[?2026h[?25l[1G⠧ [K[?25h[?2026l[?2026h[?25l[1G⠇ [K[?25h[?2026l[?2026h[?25l[1G⠏ [K[?25h[?2026l[?2026h[?25l[1G⠋ [K[?25h[?2026l[?2026h[?25l[1G⠙ [K[?25h[?2026l[?2026h[?25l[1G⠹ [K[?25h[?2026l[?2026h[?25l[1G⠸ [K[?25h[?2026l[?2026h[?25l[1G⠼ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠦ [K[?25h[?2026l[?2026h[?25l[1G⠇ [K[?25h[?2026l[?2026h[?25l[1G⠏ [K[?25h[?2026l[?2026h[?25l[1G⠋ [K[?25h[?2026l[?2026h[?25l[1G⠋ [K[?25h[?2026l[?2026h[?25l[1G⠙ [K[?25h[?2026l[?2026h[?25l[1G⠹ [K[?25h[?2026l[?2026h[?25l[1G⠸ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠴ [K[?25h[?2026l[?2026h[?25l[1G⠦ [K[?25h[?2026l[?2026h[?25l[1G⠧ [K[?25h[?2026l[?25l[?2026h[?25l[1G[K[?25h[?2026l[2K[1G[?25hError: llama runner process has terminated: cudaMalloc failed: out of memory

## 2) ollama list
NAME            ID              SIZE      MODIFIED    
llava:latest    8dd30f6b0cb1    4.7 GB    8 hours ago    
qwen2.5:3b      357c53fb659c    1.9 GB    9 hours ago    

## 3) 重測 brain 本地 /ask ×2
### 第一問
{
    "ok": true,
    "intent": "chat",
    "reply": "\u6211\u662f\u4e00\u81fa\u5c08\u9580\u5e6b\u52a9\u4f60\u7684\u8a9e\u97f3\u52a9\u7406\u3002",
    "source": "llm",
    "tts": {
        "ok": true,
        "wav": "/data/logs/tts_1787964207855.wav",
        "engine": "piper",
        "played": false,
        "play_error": "Connection failure: Access denied\n"
    }
}

### 第二問
{
    "ok": true,
    "intent": "chat",
    "reply": "\u81fa\u7063\u6700\u9ad8\u7684\u5c71\u662f\u7389\u5c71\u3002",
    "source": "llm",
    "tts": {
        "ok": true,
        "wav": "/data/logs/tts_1787964213939.wav",
        "engine": "piper",
        "played": false,
        "play_error": "Connection failure: Access denied\n"
    }
}

## 4) brain health
{
    "ok": true,
    "services": {
        "ollama": true,
        "asr": true,
        "tts": true,
        "perception": true,
        "vision": true,
        "ocr": true,
        "depth": false
    },
    "llm": "qwen2.5:3b",
    "mem_turns": 8,
    "llm_warmed": true
}
