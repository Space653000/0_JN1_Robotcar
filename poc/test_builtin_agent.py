#!/usr/bin/env python3
"""
自建代理测试 — 对照组
用来对比 OpenClaw POC 的性能
"""
import os
import sys
import time
import json
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 配置
BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:8003")

class BuiltinAgentTest:
    """自建代理测试"""

    def __init__(self):
        self.brain_url = BRAIN_URL
        logger.info(f"初始化自建代理测试")
        logger.info(f"  BRAIN: {self.brain_url}")

    def ask(self, question):
        """调用自建代理的 /ask 端点"""
        try:
            url = f"{self.brain_url}/ask"
            logger.info(f"调用自建代理: {url}")
            logger.info(f"问题: {question}")

            start_time = time.time()
            r = requests.post(
                url,
                json={"text": question},
                timeout=30
            )
            elapsed_ms = (time.time() - start_time) * 1000

            r.raise_for_status()
            data = r.json()

            logger.info(f"响应耗时: {elapsed_ms:.0f}ms")
            logger.info(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)[:300]}...")

            return {
                "response": data.get("reply", ""),
                "intent": data.get("intent", ""),
                "elapsed_ms": elapsed_ms,
                "ok": data.get("ok", False)
            }
        except Exception as e:
            logger.error(f"自建代理调用失败: {e}")
            return {"error": str(e), "elapsed_ms": 0, "ok": False}


def test_builtin_agent():
    """运行自建代理测试"""
    logger.info("="*60)
    logger.info("自建代理对照测试开始")
    logger.info("="*60)

    # 检查连接
    try:
        r = requests.get(f"{BRAIN_URL}/health", timeout=5)
        logger.info(f"✓ Brain 连接正常")
    except Exception as e:
        logger.error(f"✗ Brain 连接失败: {e}")
        return []

    # 创建 agent
    agent = BuiltinAgentTest()

    # 测试用例
    test_cases = [
        ("前面有什么", "视觉查询"),
        ("你看到了什么", "视觉查询2"),
    ]

    results = []

    for question, label in test_cases:
        logger.info(f"\n【测试】{label}: '{question}'")
        logger.info("-" * 60)

        mem_before = get_memory_usage()
        start_time = time.time()

        result = agent.ask(question)

        elapsed_total = (time.time() - start_time) * 1000
        mem_after = get_memory_usage()
        mem_delta = mem_after - mem_before

        result["test_label"] = label
        result["elapsed_total"] = elapsed_total
        result["mem_before"] = mem_before
        result["mem_after"] = mem_after
        result["mem_delta"] = mem_delta
        results.append(result)

        logger.info(f"总耗时: {elapsed_total:.0f}ms")
        logger.info(f"内存变化: {mem_delta:+.1f}MB (before: {mem_before:.1f}MB → after: {mem_after:.1f}MB)")
        logger.info("-" * 60)

        time.sleep(1)

    # 输出结果
    logger.info("\n" + "="*60)
    logger.info("自建代理测试结果汇总")
    logger.info("="*60)

    for i, r in enumerate(results, 1):
        logger.info(f"\n测试 {i}: {r.get('test_label')}")
        logger.info(f"  响应: {r.get('response', 'ERROR')[:80]}...")
        logger.info(f"  意图: {r.get('intent')}")
        logger.info(f"  总耗时: {r.get('elapsed_total', 0):.0f}ms")
        logger.info(f"  内存变化: {r.get('mem_delta', 0):+.1f}MB")

    return results


def get_memory_usage():
    """获取当前进程内存使用(MB)"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except:
        return 0.0


if __name__ == "__main__":
    results = test_builtin_agent()

    # 保存结果到文件
    log_file = "/home/jetson/0_JN1_Robotcar/poc/builtin_agent_results.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"\n结果已保存到: {log_file}")
