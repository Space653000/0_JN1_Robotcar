#!/bin/bash
# M3-6e: 如果 Kokoro 合成速度仍 >500ms/字，切换到 Piper TTS
# Piper 虽然质量略低，但合成速度通常 200-400ms/字

set -e

echo "🔄 切换 TTS 引擎到 Piper..."

# 修改 docker-compose.yml 中 TTS 服务的环境变量
sed -i 's/TTS_ENGINE=.*/TTS_ENGINE=piper/g' docker-compose.yml

echo "✅ docker-compose.yml 已修改: TTS_ENGINE=piper"
echo ""
echo "【后续步骤】"
echo "1. 重启 TTS 服务: docker-compose up -d tts"
echo "2. 等待服务启动（~10 秒）"
echo "3. 运行性能诊断: python3 ops/diagnose_tts_v2.py"
echo ""
