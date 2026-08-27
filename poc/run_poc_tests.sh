#!/bin/bash
# OpenClaw POC 测试运行脚本

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="$SCRIPT_DIR"

echo "【OpenClaw POC 测试】"
echo "时间: $(date)"
echo "工作目录: $SCRIPT_DIR"
echo "============================================================"

# 检查依赖
echo ""
echo "【检查依赖】"
python3 -c "import requests; print('✓ requests')" || (echo "✗ 缺少 requests"; exit 1)
python3 -c "import psutil; print('✓ psutil')" || echo "⚠ 缺少 psutil (可选)"

echo ""
echo "【启动 POC 测试】"
cd "$SCRIPT_DIR"
python3 openclaw_poc_agent.py 2>&1 | tee openclaw_poc_test.log

echo ""
echo "【测试完成】"
echo "日志已保存到: $LOG_DIR/openclaw_poc_test.log"
echo "结果已保存到: $LOG_DIR/openclaw_poc_results.json"
