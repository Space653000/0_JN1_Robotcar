# M33 雲端端到端確認 Sat Aug 29 12:20:42 AM UTC 2026

## 1) 重啟 cloud-gw 載入 requests 版
 Container robotcar-cloud-gw-1 Started 

## 2) cloud-gw 有正常起來?（log 尾不該有 Traceback/ImportError，要看 Uvicorn running）
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.18.0.7:42208 - "POST /ask HTTP/1.1" 200 OK
INFO:     172.18.0.1:60298 - "GET /health HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

## 3) 埠有在聽?（host /health）
{"ok":true,"has_key":true,"model":"deepseek/deepseek-chat-v3-0324:free","used_today":0}

## 4) ★直接測 /ask — source 是 openrouter（真打到）還是 error（打不到）
{
  "ok": false,
  "source": "cloud-error",
  "status": 404,
  "detail": "{\"error\":{\"message\":\"This model is unavailable for free. The paid version is available now - use this slug instead: deepseek/deepseek-chat-v3-0324\",\"code\":404},\"user_id\":\"user_3IY02ralDd8preEqTg5g6Hfa",
  "reply": null
}

## 5) ★brain->cloud-gw 內網（系統真路徑）
{"ok": false, "source": "cloud-unavailable", "reason": "circuit_open", "reply": null}

## 6) 服務數（應 9）
time="2026-08-29T08:20:52+08:00" level=warning msg="The \"WEBUI_USER\" variable is not set. Defaulting to a blank string."
time="2026-08-29T08:20:52+08:00" level=warning msg="The \"WEBUI_PASS\" variable is not set. Defaulting to a blank string."
Up 數: 9

## 7) 最終狀態確認
⚠️  打到 OpenRouter 但返回錯誤（可能是 API 問題或模型不存在）
