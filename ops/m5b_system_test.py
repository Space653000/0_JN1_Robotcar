#!/usr/bin/env python3
"""
M5b 系統綜合測試
驗證：語音迴圈 + WebUI 端對端 + 記憶 + 性能指標
"""
import os
import sys
import time
import json
import requests
from datetime import datetime
from typing import List, Dict, Any

BRAIN_URL = "http://127.0.0.1:21500"
WEBUI_URL = "http://127.0.0.1:8080"
ASR_URL = "http://127.0.0.1:8000"
TTS_URL = "http://127.0.0.1:8004"
PERCEPTION_URL = "http://127.0.0.1:8001"

class SystemTest:
    def __init__(self):
        self.results = []
        self.memory_test = []
        self.performance = {}

    def log(self, level: str, message: str):
        """日誌"""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {level:8} {message}")

    def test_health(self) -> bool:
        """測試服務健康狀態"""
        self.log("TEST", "【健康檢查】")
        services = {
            "brain": BRAIN_URL,
            "webui": WEBUI_URL,
            "asr": ASR_URL,
            "tts": TTS_URL,
            "perception": PERCEPTION_URL,
        }

        all_ok = True
        for name, url in services.items():
            try:
                r = requests.get(f"{url}/health", timeout=2)
                if r.status_code == 200:
                    self.log("PASS", f"  {name:12} online")
                else:
                    self.log("FAIL", f"  {name:12} HTTP {r.status_code}")
                    all_ok = False
            except Exception as e:
                self.log("FAIL", f"  {name:12} {str(e)[:40]}")
                all_ok = False

        return all_ok

    def test_webui_endpoints(self) -> bool:
        """測試 WebUI 各端點"""
        self.log("TEST", "【WebUI 端點測試】")

        tests = [
            ("GET", "/", "首頁"),
            ("GET", "/api/health", "健康檢查"),
            ("GET", "/api/frame", "即時畫面"),
            ("GET", "/api/perception/state", "偵測結果"),
        ]

        all_ok = True
        for method, path, desc in tests:
            try:
                if method == "GET":
                    r = requests.get(f"{WEBUI_URL}{path}", timeout=5)
                else:
                    r = requests.post(f"{WEBUI_URL}{path}", timeout=5)

                if r.status_code == 200:
                    self.log("PASS", f"  {desc:15} {r.status_code}")
                else:
                    self.log("FAIL", f"  {desc:15} {r.status_code}")
                    all_ok = False
            except Exception as e:
                self.log("FAIL", f"  {desc:15} {str(e)[:30]}")
                all_ok = False

        return all_ok

    def test_quick_actions(self) -> bool:
        """測試快捷功能"""
        self.log("TEST", "【快捷功能測試】")

        actions = [
            "state", "ocr", "describe", "faq_name", "faq_ability", "recall"
        ]

        all_ok = True
        perf = {}

        for action in actions:
            try:
                start = time.time()
                r = requests.post(
                    f"{WEBUI_URL}/api/quick-action",
                    json={"action": action},
                    timeout=30
                )
                elapsed = (time.time() - start) * 1000

                if r.status_code == 200:
                    data = r.json()
                    intent = data.get("intent", "?")
                    reply = data.get("reply", "")[:40]
                    self.log("PASS", f"  {action:12} [{intent:8}] {elapsed:6.0f}ms")
                    perf[action] = elapsed
                else:
                    self.log("FAIL", f"  {action:12} HTTP {r.status_code}")
                    all_ok = False
            except Exception as e:
                self.log("FAIL", f"  {action:12} {str(e)[:30]}")
                all_ok = False

            time.sleep(0.5)

        if perf:
            avg = sum(perf.values()) / len(perf)
            self.performance["quick_actions_avg_ms"] = avg
            self.log("INFO", f"  平均耗時: {avg:.0f}ms")

        return all_ok

    def test_dialog_flow(self) -> bool:
        """測試對話流程"""
        self.log("TEST", "【對話流程測試】")

        # 多輪對話測試記憶
        dialog_tests = [
            ("你好", "chat", "問候"),
            ("前面有什麼", "state", "視覺查詢"),
            ("能告訴我更多嗎", "chat", "追問"),
            ("你是誰", "faq_name", "FAQ"),
        ]

        all_ok = True
        total_time = 0

        for query, expected_intent, desc in dialog_tests:
            try:
                start = time.time()
                r = requests.post(
                    f"{BRAIN_URL}/ask",
                    json={"text": query},
                    timeout=30
                )
                elapsed = (time.time() - start) * 1000
                total_time += elapsed

                if r.status_code == 200:
                    data = r.json()
                    intent = data.get("intent", "?")
                    reply = data.get("reply", "")[:50]

                    self.memory_test.append({
                        "query": query,
                        "intent": intent,
                        "reply": reply,
                        "elapsed_ms": elapsed
                    })

                    if intent == expected_intent:
                        self.log("PASS", f"  {desc:8} {elapsed:6.0f}ms → [{intent}]")
                    else:
                        self.log("WARN", f"  {desc:8} 意圖 {intent} (預期 {expected_intent})")
                else:
                    self.log("FAIL", f"  {desc:8} HTTP {r.status_code}")
                    all_ok = False
            except Exception as e:
                self.log("FAIL", f"  {desc:8} {str(e)[:30]}")
                all_ok = False

            time.sleep(0.5)

        if dialog_tests:
            avg = total_time / len(dialog_tests)
            self.performance["dialog_avg_ms"] = avg
            self.log("INFO", f"  平均耗時: {avg:.0f}ms")

        return all_ok

    def test_memory_persistence(self) -> bool:
        """測試記憶持久性"""
        self.log("TEST", "【記憶系統測試】")

        try:
            # 說一個物體
            self.log("INFO", "  1. 指出物體")
            r1 = requests.post(
                f"{BRAIN_URL}/ask",
                json={"text": "杯子"},
                timeout=30
            )
            time.sleep(0.5)

            # 代詞解析
            self.log("INFO", "  2. 代詞解析")
            r2 = requests.post(
                f"{BRAIN_URL}/ask",
                json={"text": "那是什麼"},
                timeout=30
            )

            if r2.status_code == 200:
                data = r2.json()
                intent = data.get("intent", "?")
                reply = data.get("reply", "")

                if intent == "referent":
                    self.log("PASS", f"  代詞解析正常 → {reply[:40]}")
                    return True
                else:
                    self.log("WARN", f"  意圖 {intent} (預期 referent)")
                    return False
            else:
                self.log("FAIL", f"  HTTP {r2.status_code}")
                return False

        except Exception as e:
            self.log("FAIL", f"  {str(e)[:40]}")
            return False

    def test_hallucination_guard(self) -> bool:
        """測試防幻覺"""
        self.log("TEST", "【防幻覺測試】")

        try:
            r = requests.post(
                f"{BRAIN_URL}/ask",
                json={"text": "現在有龍嗎"},
                timeout=30
            )

            if r.status_code == 200:
                reply = r.json().get("reply", "")

                if any(word in reply for word in ["沒有", "沒看到", "沒發現"]):
                    self.log("PASS", f"  防幻覺正常 → {reply[:40]}")
                    return True
                else:
                    self.log("WARN", f"  回覆未展現防幻覺 → {reply[:40]}")
                    return False
            else:
                self.log("FAIL", f"  HTTP {r.status_code}")
                return False

        except Exception as e:
            self.log("FAIL", f"  {str(e)[:40]}")
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """執行所有測試"""
        self.log("INFO", "=" * 60)
        self.log("INFO", "M5b 系統綜合測試開始")
        self.log("INFO", "=" * 60)

        results = {
            "health": self.test_health(),
            "webui_endpoints": self.test_webui_endpoints(),
            "quick_actions": self.test_quick_actions(),
            "dialog_flow": self.test_dialog_flow(),
            "memory": self.test_memory_persistence(),
            "hallucination_guard": self.test_hallucination_guard(),
        }

        self.log("INFO", "=" * 60)
        self.log("INFO", "【測試結果摘要】")

        passed = sum(1 for v in results.values() if v)
        total = len(results)

        for test, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            self.log("INFO", f"  {test:20} {status}")

        self.log("INFO", f"  通過: {passed}/{total}")
        self.log("INFO", "=" * 60)

        return {
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "performance": self.performance,
            "memory_test": self.memory_test,
            "summary": f"{passed}/{total} tests passed"
        }


def main():
    tester = SystemTest()
    report = tester.run_all_tests()

    # 保存報告
    report_file = "/home/jetson/0_JN1_Robotcar/data/vision_snapshots/M5b_system_test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 測試報告已保存: {report_file}")

    # 打印性能指標
    if report["performance"]:
        print("\n【性能指標】")
        for key, value in report["performance"].items():
            print(f"  {key}: {value:.0f}ms")

    return 0 if all(report["results"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
