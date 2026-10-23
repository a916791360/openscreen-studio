@echo off
chcp 65001 >nul
echo =======================================================
echo 🎬 OpenScreen Studio · 软件教程自动化视频工作台
echo =======================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ [错误] 未检测到 python，请先安装 Python 3.9 或更高版本。
    echo 👉 官网下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo ⚠️ [提示] 未检测到 FFmpeg，音视频合并与字幕压制功能需要 FFmpeg。
    echo 👉 Windows 推荐安装: 打开终端执行 winget install Gyan.FFmpeg
    echo -------------------------------------------------------
)

if not exist ".venv" (
    echo 📦 [初始化] 首次运行，正在创建独立 Python 虚拟环境 (.venv)...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo 📥 [安装依赖] 正在安装 edge-tts 神经网络语音引擎...
    python -m pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo ✅ 依赖环境配置完成！
) else (
    call .venv\Scripts\activate.bat
)

if not exist "output" mkdir output
if not exist "uploads" mkdir uploads

echo 🚀 正在启动工作台服务器: http://localhost:8765 ...
start http://localhost:8765
python studio.py
pause
