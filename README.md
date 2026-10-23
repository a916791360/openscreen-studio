# 🎬 OpenScreen Studio · 软件教程自动化视频工作台

> **“录屏动效自动卡点，AI 大模型严控时长，免 Key 主持人级配音，一键音画字幕秒级出片。”**  
> 专为制作高质量 SaaS 功能演示、后台系统操作教程、产品更新讲解打造的现代化工作台。

---

## 🌟 为什么需要 OpenScreen Studio？

制作高质量软件教程视频通常有三大门槛：
1. **录屏平淡生硬**：普通录屏没有重点，观众看不清鼠标点击在哪里。
2. **解说音画脱节**：录完视频自己配音容易卡顿、语速不一，或者解说还没说完视频就放完了。
3. **后期剪辑费时**：手动对轴、卡点字幕、分段剪辑极其消耗精力。

**OpenScreen Studio + OpenScreen** 组合拳彻底解决这一流程：
- 📸 **录制端（OpenScreen）**：自动捕捉鼠标轨迹，生成专业级平滑镜头缩放、圆角阴影与弹簧光标动效。
- 🧠 **编导端（OpenScreen Studio）**：自动读取录屏工程的**镜头特写与点击交互节拍**，根据视频物理秒数，由大模型（DeepSeek / OpenAI / 智谱等）按分镜**严卡字数预算**，自动撰写音画严密卡点的解说词。
- 🎙️ **合成端（Edge-TTS + FFmpeg）**：搭载微软顶级多角色神经网络自然语音（晓晓、云希等），毫秒级对齐压制字幕，画面末尾自动定格保底，一键导出成品 MP4！

---

## 🚀 3 步极速上手

### 第一步：安装录屏工具 OpenScreen
OpenScreen 是一款优秀的开源录屏工具（开源版 Screen Studio）。请根据您的操作系统下载安装：

| 平台 | 官方直接下载链接 |
| :--- | :--- |
| **macOS (Apple Silicon M1/M2/M3/M4)** | [Openscreen-macOS-Apple-Silicon-2.1.2.dmg](https://github.com/getopenscreen/openscreen/releases/download/v2.1.2/Openscreen-macOS-Apple-Silicon-2.1.2.dmg) |
| **macOS (Intel 芯片)** | [Openscreen-macOS-Intel-2.1.2.dmg](https://github.com/getopenscreen/openscreen/releases/download/v2.1.2/Openscreen-macOS-Intel-2.1.2.dmg) |
| **Windows (x64)** | [Openscreen.Setup.2.1.2-x64.exe](https://github.com/getopenscreen/openscreen/releases/download/v2.1.2/Openscreen.Setup.2.1.2-x64.exe) |
| **Linux (AppImage)** | [Openscreen-Linux-2.1.2.AppImage](https://github.com/getopenscreen/openscreen/releases/download/v2.1.2/Openscreen-Linux-2.1.2.AppImage) |

*（也可访问 [OpenScreen 官方 Releases 仓库](https://github.com/getopenscreen/openscreen/releases) 获取最新版）*

---

### 第二步：克隆并启动工作台
确保电脑已安装 `python3` (3.9+) 与 `ffmpeg`。

```bash
# 1. 克隆代码并进入目录
git clone <您的私有仓库地址>
cd openscreen-studio

# 2. 一键运行（自动创建独立虚拟环境并打开浏览器）
# macOS / Linux 用户终端运行：
./start.sh

# Windows 用户直接双击运行：
start.bat
```

> **系统依赖提示**：
> - **macOS**：如未安装 FFmpeg，终端执行 `brew install ffmpeg` 即可。
> - **Windows**：终端执行 `winget install Gyan.FFmpeg`。

服务启动后，浏览器将自动打开工作台：**`http://localhost:8765`**。

---

### 第三步：配置您自己的大模型 (LLM)

首次使用，点击工作台右上角的 **「模型与提示词设置」**：
1. **选择服务商预设**：支持 **DeepSeek**（高性价比推荐）、**OpenAI**、**智谱 GLM**、**硅基流动** 或 **本地 Ollama**。
2. **填入 API Key**：输入您的 API 密钥，点击 **「测试连通性」** 验证是否握手成功。
3. **点击保存**：配置仅加密保存在本地的 `llm_config.json` 中，受 `.gitignore` 保护，**绝对不会上传或泄露**。

---

## 🎬 极速出片工作流

1. **录制**：打开 OpenScreen 录制一段功能操作（无须出声说话），点击导出为 MP4（如保存到“下载”目录）。
2. **选择**：刷新工作台左下角「录屏媒体库」，系统会自动**秒级匹配**到对应的 OpenScreen 运镜底稿与遥测节拍。
3. **输入要点**：在右侧大文本框输入粗略的操作要点（如：`进入工单管理，新建工单，输入故障现象，指定给张工并提交`）。
4. **智能拟合**：点击上方 **「智能拟合分镜文案」**。AI 会根据特写聚焦、主操作区等时间节拍，严格将字数限制在对应秒数内，生成卡点分镜解说。
5. **试听与调整**：在左下角选择心仪的配音员（如「晓晓」亲和女声或「云希」活力男声），点击微标试听；微调语速基准。
6. **一键出片**：点击底部 **「导出成片 (渲染视频 + AI配音 + 同步字幕)」**，系统自动进行音视频合成与字幕压制，提供一键下载与即时播放！

---

## 📂 项目结构说明

```
openscreen-studio/
├── studio.py                   # 工作台核心多线程服务与 Range-streaming 播放器
├── ai_script_generator.py      # OpenScreen 遥测节拍解析器与大模型时长约束编导引擎
├── generate_tutorial_audio.py  # 独立命令行音频/字幕生成器 (基于 Edge-TTS)
├── tokens.css                  # Linear / Raycast 级工业质感设计系统变量
├── sample_tutorial.txt         # 示范台词样本
├── requirements.txt            # Python 核心依赖 (edge-tts)
├── start.sh                    # 一键极速启动脚本
├── AGENTS.md                   # 针对 AI 助手 (Cursor/Claude/Antigravity) 的自动部署指引
└── llm_config.example.json     # 大模型配置模板 (用户填写的真实 Key 本地保留，不上传)
```

---

## 💡 常见问题 Q&A

### Q1：Edge-TTS 需要付费购买 API Key 吗？
**答：完全不需要！** 项目内置微软 Edge 神经网络语音合成引擎，直接调用官方超高拟真声音，音质细腻自然，完全免费免 Key。

### Q2：如果视频时长较短，AI 润色的台词来不及念完怎么办？
**答：双重硬保障！**
1. **前端与大模型严卡字数**：大模型会按 $4.3 \text{ 字/秒}$ 物理速率严格受限，分镜卡片会实时以绿色标明「字数卡准」。
2. **画面末尾定格保底 (Hold Last Frame)**：即便语速出现微小偏差，系统默认开启保底机制——视频最后一帧自动静止延长，直到配音完整念完，绝不生硬截断语音！

### Q3：如果是同事让 AI 助手帮他安装配置，能直接用吗？
**答：完全可以！** 项目根目录附带了专门为 AI 助手设计的 `AGENTS.md`。同事把代码下载后，直接把仓库交给 Cursor、Claude 或 Antigravity，输入 *“请帮我安装并运行这个项目”*，AI 助手就会自动完成所有环境装配并启动服务。

---

## 📄 开源与隐私协议
- 本项目严格保证用户隐私：所有视频处理均在本地离线执行；大模型调用仅请求用户配置的官方 API 地址；绝不包含任何硬编码凭据。
