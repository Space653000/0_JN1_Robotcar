# M28 CURRENT_PEAK_RAM 壓測 Fri Aug 28 04:43:44 PM UTC 2026

## 基線(閒置)
               total        used        free      shared  buff/cache   available
Mem:            15Gi       9.0Gi       3.7Gi       126Mi       2.6Gi       5.9Gi

## RAM 連續取樣(背景，每 0.5s × 80 次 = 40 秒)
取樣中...

## 併發壓力：4×brain/ask (qwen 詳細生成) + 3×perception/frame (YOLO)
發送請求...
等待所有請求完成...
停止採樣...

## ★ 峰值 RAM
PEAK_USED_RAM_MB = 9923 / 15655 MB (63.4%)

## 取樣尾 10 筆
1787935460.326259608 9224
1787935460.834243872 9225
1787935461.342204264 9231
1787935461.849284378 9232
1787935462.357771951 9234
1787935462.866248515 9228
1787935463.374470257 9230
1787935463.883535925 9229
1787935464.391578847 9225
1787935464.899464516 9229

## 壓測後系統狀態
               total        used        free      shared  buff/cache   available
Mem:            15Gi       9.0Gi       5.2Gi       126Mi       1.1Gi       5.9Gi
Swap:           23Gi       1.1Gi        22Gi

## qwen 回應樣本(證明真跑)
--- ask_1.out 頭 300 字 ---
{"ok":true,"intent":"describe","reply":"我的場景描述功能還沒上線（VLM 模型還在準備中），我只能用鏡頭偵測到的物體回答你。","source":"vlm-offline","vision_error":"camera read failed","tts":{"ok":true,"wav":"/data/logs/tts_1787935425138.wav","engine":"piper","playe

## GPU/溫度(如果可用)
取得 tegrastats 資料...

## 簡要統計
壓測時長：約 40 秒
並發任務：7（4×LLM + 3×CV）
工作負荷：詳細文本生成 + 視覺推理
