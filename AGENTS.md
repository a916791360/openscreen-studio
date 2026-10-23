# AGENTS.md · AI 助手运行指南

欢迎使用 **OpenScreen Studio**。如果你是正在协助人类用户配置或运行本项目的 AI 编码助手（如 Claude, Cursor, Copilot, Antigravity, ChatGPT 等），请严格遵循本指南以实现秒级零故障部署。

---

## 1. 项目核心概述
本项目是一个**软件教程视频自动化制作工作台**，专为搭配开源屏幕录制工具 [OpenScreen](https://github.com/getopenscreen/openscreen) 设计。
- **核心能力**：
  1. 自动读取 OpenScreen 录屏的鼠标交互与特写镜头节拍（Telemetry Zoom & Click Beats）。
  2. 严卡视频物理秒数，利用大模型（DeepSeek / OpenAI / 智谱等）智能生成音画严密卡点的分镜解说词。
  3. 基于微软 Edge-TTS 神经网络引擎（免任何 Key），生成主持人级配音与精准字幕。
  4. 利用 FFmpeg 完成画面保底定格防截断、配音与字幕压制，一键直接出片。

---

## 2. 外部依赖清单
运行前请协助用户确认以下依赖环境：
1. **Python 3.9+**（项目主要基于标准库 + `edge-tts`）。
2. **FFmpeg**（音视频流合成与字幕压制必需）：
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg`
   - Windows: `winget install Gyan.FFmpeg` 或 `choco install ffmpeg`
3. **OpenScreen 录屏软件**（生成带鼠标追踪与平滑缩放动效的视频源）：
   - GitHub 官方下载：`https://github.com/getopenscreen/openscreen/releases`

---

## 3. 一键启动流程
直接在项目根目录运行预置启动脚本：
```bash
./start.sh
```
`start.sh` 会自动检测 Python 与 FFmpeg、创建 `.venv` 虚拟环境、安装 `requirements.txt`、并在默认浏览器自动打开 `http://localhost:8765`。

如果手动分步启动：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 studio.py
```

---

## 4. 大模型配置交互
- 用户无需手动修改代码或在环境变量中埋入 API Key。
- 启动后引导用户在网页右上角点击 **「模型与提示词设置」** 弹窗：
  - 支持 **DeepSeek**（推荐，经济且逻辑极强）、**OpenAI**、**智谱 GLM**、**硅基流动** 或 **本地 Ollama**。
  - 用户输入 API Key 后点击「测试连通性」即可完成自检。
  - 配置保存在本地 `llm_config.json`，已受 `.gitignore` 保护，永不外泄。

---

## 5. 项目核心架构
- `studio.py`：多线程 HTTP 服务器，承载工作台前端界面、媒体视频分块流传输（HTTP 206 Range）、遥测节拍解析与 FFmpeg 合成出片调用。
- `ai_script_generator.py`：运镜节拍智能算法、分镜字数预算评估、大模型 Prompt 模板与双向字数严卡控制。
- `generate_tutorial_audio.py`：独立 CLI 配音脚本，支持快速将文本转为高保真音频与 `.srt` / `.vtt` 字幕。
- `tokens.css`：符合 Linear / Raycast 质感的无 Emoji 专业设计系统样式变量。
