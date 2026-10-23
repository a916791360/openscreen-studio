# AGENTS.md · AI 助手运行与配置执行手册

> **致正在协助人类用户的 AI 助手（Cursor, Claude Code, Copilot, Antigravity, Windsurf, OpenCode 等）：**  
> 本手册为你提供了本项目的完整架构图谱、快速安装流水线、排错机制以及**如何引导并协助用户制作专属声音克隆**的标准流程。请严格阅读并遵照执行。

---

## 1. 核心定位与双轨音色架构

本项目是一个专为开源录屏工具 [OpenScreen](https://github.com/getopenscreen/openscreen) 打造的**自动化软件教程视频工作台**。

### 音色支持双轨机制（重要概念）：
1. **标准音色（开箱即用 · 默认激活）**：
   - 基于微软 Edge-TTS（内置晓晓、云希、云健等预置角色）；
   - **特点**：0 显卡要求、免 API Key、秒级生成，安装基础依赖后直接可用。
2. **私有专属音色（1:1 声线复刻 · 按需激活）**：
   - 基于 F5-TTS 零样本 Flow-Matching 扩散模型 + 原生字轨毫秒级对齐 + 广播级母带处理链；
   - **特点**：用户只需提供 10~15 秒录音，系统即可提取声线特征，生成完全由用户原声配音+精准 Apple 风格黑底字幕的教程视频。100% 保持输入文案原文，彻底杜绝 ASR 听写错别字（如将“工单”识别为“供丹”）。

---

## 2. 协助用户初次安装与启动

当用户要求“运行/安装这个项目”时，请按以下顺序执行：

### Step 1: 检查前置系统环境
- **Python**：确认 Python 版本 $\ge 3.9$ (`python3 --version`)；
- **FFmpeg**：确认系统已安装 FFmpeg (`ffmpeg -version`)。若未安装：
  - macOS: `brew install ffmpeg`
  - Windows: `winget install Gyan.FFmpeg`
  - Linux: `sudo apt update && sudo apt install -y ffmpeg`

### Step 2: 执行一键启动
优先直接执行预置的启动脚本：
```bash
# macOS / Linux
./start.sh

# Windows
start.bat
```
或者手动装配：
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 studio.py
```

### Step 3: 告知用户如何开始
启动完成后，提示用户：
1. 浏览器打开 `http://localhost:8765`；
2. 在右上角「模型与提示词设置」填入其常用大模型（如 DeepSeek / OpenAI）的 API Key；
3. 当前已默认提供**晓晓、云希**等标准音色。如果用户想用自己的声音配音，直接对你说：*“我想制作我自己的专属声音”* 即可。

---

## 3. 当用户提出“我想制作/使用我自己的音色”时的标准执行流程

**不要让用户手动去配置复杂的代码和参数！** 作为 AI 助手，请全自动引导并协助用户完成闭环：

### 流程 1：向用户提供清晰的录音指导与范例文本
请礼貌回复用户：
> *“没问题！制作专属声音非常简单，你只需用手机录音机录制一段 10~15 秒的自然人声。录制时请找一个安静房间，嘴巴距离手机 15 厘米，用平时给同事讲解演示的自信语速朗读以下示范文案：*
>
> 🎙️ **建议朗读文案**：  
> *‘大家好，欢迎观看系统功能实操教学。在本期教程中，我将带大家快速了解如何在后台处理新建工单与服务派发流程。’*
>
> *录制完成后，把音频文件（.m4a 或 .wav）拖到对话框发给我，剩下的环境与配置我来帮你搞定！”*

### 流程 2：音频预处理与入库
收到用户的音频文件后，由你通过命令完成预处理：
```bash
# 1. 规范化并转为 24kHz 高品质 WAV
ffmpeg -y -i "用户音频路径" \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11,highpass=f=80" \
  -ar 24000 -ac 1 "custom_voice/用户姓名_voice.wav"
```

### 流程 3：在 `custom_voice/voices.json` 中自动注册
在 `custom_voice/voices.json` 中追加用户的音色卡片配置：
```json
[
  {
    "id": "my_voice",
    "name": "用户姓名 (专属原声)",
    "role": "产品专家 · 1:1复刻",
    "tag": "F5-TTS · 专属音色模型",
    "ref_audio": "用户姓名_voice.wav",
    "ref_text": "录音中所朗读的准确文字内容"
  }
]
```

### 流程 4：自动安装声音克隆扩展依赖
检查当前虚拟环境，执行：
```bash
pip install -r requirements-voice.txt
```
*(注意：在 macOS Apple Silicon 上，项目内建的 `custom_voice_tts.py` 已自动适配 MPS 硬件加速并绕过系统动态库冲突；在 Windows/Linux 上自动调用 CUDA 或 CPU)*

### 流程 5：执行自检并通知用户
运行一次快速测试：
```bash
python3 custom_voice_tts.py --text "你好，这是我使用自己的专属音色合成的测试语音。" --output-audio "output/preview_my_voice.mp3" --output-srt "output/preview_my_voice.srt"
```
测试通过后，通知用户：
> *“🎉 你的专属音色已录入并激活完成！请刷新浏览器页面 `http://localhost:8765`，在 STAGE 2 中点击属于你的【专属原声】卡片试听，即可开始一键出片！”*

---

## 4. 关键文件与架构速查

- `studio.py`：工作台核心服务。动态扫描 `custom_voice/voices.json`，无缝加载所有专属音色。
- `custom_voice_tts.py`：专属音色核心合成引擎（基于 F5-TTS 扩散推理与原文原生字轨毫秒级对齐，内置广播级母带人声增强 EQ）。
- `custom_voice/`：团队音色资源池。
  - `voices.json`：音色注册表（支持多人并存）。
  - `*.wav`：各同事的参考音频切片。
- `ai_script_generator.py`：OpenScreen 遥测节拍解析器与字数时长硬卡控编导引擎。
- `llm_config.json`：本地保存的用户大模型配置（已受 `.gitignore` 保护，绝不提交）。

---

## 5. 常见技术故障排查 (Troubleshooting)

1. **macOS 下出现 PyTorch / TorchCodec 动态库缺失**：
   `custom_voice_tts.py` 内部已对 `torchaudio.load` 进行了 monkeypatch，使用原生 `soundfile` 读取音频，切勿重新安装旧版 torchcodec。
2. **MPS 多批次并发退出码 139 (SIGSEGV)**：
   `f5-tts` 在 MPS 架构上不支持多线程并发，`utils_infer.py` 已调整为单线程顺序流推理，切勿将其改回 `ThreadPoolExecutor`。
3. **零错别字原生字轨对齐**：
   系统废除了 ASR 听写反推字幕，改为在逐句合成时由物理波形长度直接对齐字幕时间戳，保证 100% 呈现用户输入的原文。
