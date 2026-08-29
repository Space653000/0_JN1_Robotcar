# M34 換現行免費模型 Sat Aug 29 12:24:18 AM UTC 2026

## 1) 自動撈現行免費模型並挑一個
✅ 選用模型: 

## 2) 設進 .env(覆蓋既有) + server.py 預設(版控)
✅ .env 已更新：
OPENROUTER_MODEL=

✅ server.py 預設已更新：
MODEL = os.environ.get("OPENROUTER_MODEL","")

## 3) 重啟 cloud-gw
 Container robotcar-cloud-gw-1 Started 

## 4) ★真測 /ask — 這次要 source:openrouter + 真 reply
提問：用一句話說明什麼是 ROS2
{
  "ok": false,
  "source": "cloud-error",
  "status": 404,
  "detail": "{\"error\":{\"message\":\"This model is unavailable for free. The paid version is available now - use this slug instead: deepseek/deepseek-chat-v3-0324\",\"code\":404},\"user_id\":\"user_3IY02ralDd8preEqTg5g6Hfa",
  "reply": null
}

## 5) 等斷路器過，測 brain->cloud-gw 系統真路徑
等待 30 秒（斷路器冷卻中）...
測試 brain 連接 cloud-gw：
{"ok": false, "source": "cloud-error", "status": 404, "detail": "{\"error\":{\"message\":\"This model is unavailable for free. The paid version is available now - use this slug instead: deepseek/deepseek-chat-v3-0324\",\"code\":404},\"user_id\":\"user_3IY02ralDd8preEqTg5g6Hfa", "reply": null}

## 6) gateway 用量計數
{"ok":true,"has_key":true,"model":"deepseek/deepseek-chat-v3-0324:free","used_today":2}
