@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =======================================================
echo 🎬 OpenScreen Studio · 软件教程自动化视频工作台
echo =======================================================

:: 1. 查找可用 Python 命令 (优先 python，备选 py)
set "PY_CMD=python"
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        set "PY_CMD=py"
    ) else (
        echo ❌ [错误] 未检测到 Python，请先安装 Python 3.9 或更高版本。
        echo 👉 官网下载: https://www.python.org/downloads/
        echo 💡 提示：安装时请务必勾选 "Add python.exe to PATH"
        pause
        exit /b 1
    )
)

:: 2. 检查 FFmpeg
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo ⚠️ [提示] 未检测到 FFmpeg，成片导出与字幕压制需要 FFmpeg。
    echo 👉 Windows 快速安装方法: 打开终端运行 winget install Gyan.FFmpeg
    echo -------------------------------------------------------
)

:: 3. 准备虚拟环境
if not exist ".venv" (
    echo 📦 [初始化] 首次运行，正在创建独立 Python 虚拟环境 (.venv)...
    %PY_CMD% -m venv .venv
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

echo 🚀 正在启动工作台服务器，即将自动打开浏览器...
python studio.py
pause
