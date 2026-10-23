#!/usr/bin/env bash
# =======================================================
# 🎬 OpenScreen Studio 一键极速启动脚本
# =======================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "======================================================="
echo "🎬 OpenScreen Studio · 软件教程自动化视频工作台"
echo "======================================================="

# 1. 检查 Python 3 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ [错误] 未检测到 python3，请先安装 Python 3.9 或更高版本。"
    echo "👉 macOS 推荐安装: brew install python3"
    exit 1
fi

# 2. 检查 FFmpeg 核心依赖 (用于音视频合并与字幕压制)
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️ [提示] 未检测到 FFmpeg，成片导出与字幕压制功能需要 FFmpeg。"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "👉 macOS 快速安装: brew install ffmpeg"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "👉 Linux 快速安装: sudo apt update && sudo apt install -y ffmpeg"
    fi
    echo "-------------------------------------------------------"
fi

# 3. 准备虚拟环境与安装依赖
if [ ! -d ".venv" ]; then
    echo "📦 [初始化] 首次运行，正在创建独立 Python 虚拟环境 (.venv)..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "📥 [安装依赖] 正在安装 edge-tts 神经网络语音引擎..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo "✅ 依赖环境配置完成！"
else
    source .venv/bin/activate
fi

# 4. 创建本地产物目录
mkdir -p output uploads

# 5. 启动 Studio 服务
PORT="${PORT:-8765}"
echo "🚀 正在启动工作台服务器: http://localhost:$PORT ..."

# 如果端口已被旧进程占用，先优雅提示
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "ℹ️ 检测到端口 $PORT 已有进程运行，正在切换为活动服务..."
fi

# 启动服务
python3 studio.py "$PORT" &
SERVER_PID=$!

sleep 1.2

# 6. 自动唤起浏览器
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:$PORT"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:$PORT" 2>/dev/null || true
fi

echo "======================================================="
echo "🎉 工作台已在浏览器打开: http://localhost:$PORT"
echo "👉 提示：按 Ctrl+C 可停止当前服务"
echo "======================================================="

wait $SERVER_PID
