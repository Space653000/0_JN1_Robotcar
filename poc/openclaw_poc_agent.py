#!/usr/bin/env python3
"""
OpenClaw POC Agent — 最小化集成测试
目标：验证 OpenClaw 是否能集成我们的工具并正确应答
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
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b")
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://127.0.0.1:8001")

class OpenClawPOCAgent:
    """最小化 OpenClaw POC Agent"""

    def __init__(self):
        self.model = LLM_MODEL
        self.ollama_url = OLLAMA_URL
        self.perception_url = PERCEPTION_URL
        self.tools_defined = False
        self.memory = []
        logger.info(f"初始化 OpenClaw POC Agent")
        logger.info(f"  OLLAMA: {self.ollama_url}")
        logger.info(f"  MODEL: {self.model}")
        logger.info(f"  PERCEPTION: {self.perception_url}")

    def register_tools(self):
        """注册可用工具定义"""
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_perception_state",
                    "description": "获取前方摄像头视觉感知结果（什么物体、位置、距离）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "查询类型：location/objects/distance"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        self.tools_defined = True
        logger.info(f"已注册 {len(self.tools)} 个工具")

    def call_perception(self, query="state"):
        """调用我们的 perception /state 服务"""
        try:
            url = f"{self.perception_url}/state"
            logger.info(f"调用 perception: {url}")
            r = requests.post(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            logger.info(f"perception 响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return data
        except Exception as e:
            logger.error(f"perception 调用失败: {e}")
            return {"error": str(e)}

    def process_tool_call(self, tool_name, tool_input):
        """处理 LLM 的工具调用"""
        logger.info(f"LLM 请求使用工具: {tool_name}")

        if tool_name == "get_perception_state":
            query = tool_input.get("query", "state")
            result = self.call_perception(query)
            return json.dumps(result, ensure_ascii=False)
        else:
            return json.dumps({"error": f"未知工具: {tool_name}"})

    def chat(self, user_input, system_prompt=None):
        """与 LLM 对话，支持工具调用"""
        if not self.tools_defined:
            self.register_tools()

        if system_prompt is None:
            system_prompt = (
                "你是一个机器车上的语音助理。"
                "用繁体中文、口语、简洁地回答。"
                "当用户询问视觉信息时，你应该使用 get_perception_state 工具。"
                "严禁编造视觉感知信息，只根据真实的工具返回结果回答。"
            )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.memory)
        messages.append({"role": "user", "content": user_input})

        logger.info(f"用户输入: {user_input}")

        # 调用 LLM（支持工具调用）
        try:
            start_time = time.time()

            r = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": messages,
                    "tools": self.tools,
                    "options": {"num_ctx": 2048}
                },
                timeout=60
            )
            r.raise_for_status()
            response = r.json()
            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(f"LLM 响应耗时: {elapsed_ms:.0f}ms")

            # 检查是否有工具调用
            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                logger.info(f"LLM 请求工具调用: {len(tool_calls)} 个")
                # 处理工具调用
                for tool_call in tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_input = tool_call.get("function", {}).get("arguments", {})
                    logger.info(f"  工具: {tool_name}, 参数: {tool_input}")

                    tool_result = self.process_tool_call(tool_name, tool_input)
                    logger.info(f"  工具结果: {tool_result[:100]}...")

                    # 将工具调用和结果加回对话
                    messages.append(message)
                    messages.append({
                        "role": "tool",
                        "content": tool_result
                    })

                # 再次调用 LLM 获取最终响应
                logger.info("再次调用 LLM 获取最终响应...")
                r2 = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "messages": messages,
                        "options": {"num_ctx": 2048}
                    },
                    timeout=60
                )
                r2.raise_for_status()
                final_response = r2.json()
                content = final_response.get("message", {}).get("content", "").strip()
            else:
                content = message.get("content", "").strip()

            # 更新记忆
            self.memory.append({"role": "user", "content": user_input})
            self.memory.append({"role": "assistant", "content": content})
            if len(self.memory) > 16:  # 限制记忆大小
                self.memory = self.memory[-16:]

            logger.info(f"最终响应: {content}")
            return {
                "response": content,
                "used_tools": len(tool_calls) > 0,
                "elapsed_ms": elapsed_ms
            }

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {"error": str(e), "elapsed_ms": 0}


def test_openclaw_poc():
    """运行 POC 测试"""
    logger.info("="*60)
    logger.info("OpenClaw POC 测试开始")
    logger.info("="*60)

    # 检查 ollama 连接
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        logger.info(f"✓ Ollama 连接正常")
    except Exception as e:
        logger.error(f"✗ Ollama 连接失败: {e}")
        return

    # 检查 perception 连接
    try:
        r = requests.post(f"{PERCEPTION_URL}/state", timeout=5)
        logger.info(f"✓ Perception 连接正常")
    except Exception as e:
        logger.error(f"✗ Perception 连接失败: {e}")
        return

    # 创建 agent
    agent = OpenClawPOCAgent()

    # 测试用例
    test_cases = [
        ("前面有什么", "视觉查询"),
        ("你看到了什么", "视觉查询2"),
    ]

    results = []

    for user_input, label in test_cases:
        logger.info(f"\n【测试】{label}: '{user_input}'")
        logger.info("-" * 60)

        mem_before = get_memory_usage()
        start_time = time.time()

        result = agent.chat(user_input)

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
    logger.info("POC 测试结果汇总")
    logger.info("="*60)

    for i, r in enumerate(results, 1):
        logger.info(f"\n测试 {i}: {r.get('test_label')}")
        logger.info(f"  响应: {r.get('response', 'ERROR')[:80]}...")
        logger.info(f"  使用工具: {r.get('used_tools')}")
        logger.info(f"  LLM耗时: {r.get('elapsed_ms', 0):.0f}ms")
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
    results = test_openclaw_poc()

    # 保存结果到文件
    log_file = "/home/jetson/0_JN1_Robotcar/poc/openclaw_poc_results.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"\n结果已保存到: {log_file}")
