#!/usr/bin/env bash
# =======================================================
# 🎬 OpenScreen Studio Desktop Runner (后台静默拉起器)
# =======================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. 优先探测是否已有实例运行 (8765 ~ 8774)，秒级激活，杜绝重复进程
for P in {8765..8774}; do
    if curl -s --max-time 0.6 "http://127.0.0.1:$P/api/voices" 2>/dev/null | grep -q "zh-CN-XiaoxiaoNeural"; then
        open "http://localhost:$P"
        osascript -e "display notification \"工作台已在后台运行中，已激活浏览器窗口\" with title \"OpenScreen Studio\"" 2>/dev/null || true
        exit 0
    fi
done

# 2. 准备运行目录
mkdir -p output uploads

# 3. 确定 Python 解释器 (优先使用虚拟环境)
PYTHON_EXEC="python3"
if [ -f "$DIR/.venv/bin/python3" ]; then
    PYTHON_EXEC="$DIR/.venv/bin/python3"
elif [ -f "$DIR/.venv_tts/bin/python3" ]; then
    PYTHON_EXEC="$DIR/.venv_tts/bin/python3"
fi

# 4. 启动后台服务并记录日志
nohup "$PYTHON_EXEC" studio.py > app.log 2>&1 </dev/null &

# 5. 轮询等待服务监听就绪
for i in {1..20}; do
    for P in {8765..8774}; do
        if curl -s --max-time 0.5 "http://127.0.0.1:$P/api/voices" 2>/dev/null | grep -q "zh-CN-XiaoxiaoNeural"; then
            open "http://localhost:$P"
            osascript -e "display notification \"工作台启动就绪 (http://localhost:$P)\" with title \"OpenScreen Studio\"" 2>/dev/null || true
            exit 0
        fi
    done
    sleep 0.4
done

# 兜底直接打开默认端口
open "http://localhost:8765"
