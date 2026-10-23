#!/usr/bin/env python3
"""
ASC 专属音色克隆合成引擎 (基于 F5-TTS Zero-Shot + Faster-Whisper 自动时间戳对齐)
针对 Apple Silicon M 系列芯片深度优化。
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / ".venv_tts/bin/python"
CUSTOM_VOICE_DIR = BASE_DIR / "custom_voice"
REF_AUDIO_PATH = CUSTOM_VOICE_DIR / "ref_clip_engineer.wav"
REF_TEXT = "工程师接单后，移动端会立即收到推送提醒，包括精准的客户地址。"

def format_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msecs = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

def get_optimal_device() -> str:
    try:
        import torch
        if sys.platform == "darwin" and torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"

def synthesize_custom_voice(text: str, output_audio: Path, output_srt: Path, speed: float = 1.0, ref_audio: Path = None, ref_text: str = None):
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    temp_wav = output_audio.with_suffix(".wav")
    
    active_ref_audio = ref_audio or REF_AUDIO_PATH
    active_ref_text = ref_text or REF_TEXT
    device = get_optimal_device()

    clean_text = " ".join([line.strip() for line in text.splitlines() if line.strip()])
    print(f"🎙️ [1/3] 正在通过 F5-TTS 专属音色模型合成配音 (加速步数: 16, 设备: {device})...")
    cli_cmd = [
        str(VENV_PYTHON),
        str(BASE_DIR / ".venv_tts/bin/f5-tts_infer-cli"),
        "-m", "F5TTS_Base",
        "-r", str(active_ref_audio),
        "-s", active_ref_text,
        "-t", clean_text,
        "-o", str(temp_wav.parent),
        "-w", temp_wav.name,
        "--nfe_step", "16",
        "--speed", str(speed),
        "--device", device
    ]
    
    res = subprocess.run(cli_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"⚠️ MPS 异常，回退 CPU 模式重试: {res.stderr[:200]}")
        cli_cmd[-1] = "cpu"
        res = subprocess.run(cli_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"F5-TTS 合成失败: {res.stderr}")

    # 将生成的 wav 经专业广播母带链处理 (提亮高频、人声动态压限与智能响度)
    print(f"🎵 [2/3] 正在通过广播级人声母带链增强清晰度并编码 MP3...")
    vocal_master_filter = (
        "highpass=f=80,"
        "equalizer=f=3200:t=q:w=1.2:g=3.2,"
        "treble=g=4.5:f=6500,"
        "compand=attacks=0.03:decays=0.3:points=-80/-80|-40/-28|-20/-12|0/-5:soft-knee=6,"
        "loudnorm=I=-16:TP=-1.5:LRA=8"
    )
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", str(temp_wav),
        "-af", vocal_master_filter,
        "-b:a", "192k",
        str(output_audio)
    ]
    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 调用 Faster-Whisper 提取精准时间轴并生成 SRT
    print(f"📝 [3/3] 正在通过 Faster-Whisper 提取高精度时间轴字幕...")
    whisper_script = f"""
from faster_whisper import WhisperModel
model = WhisperModel('small', device='cpu', compute_type='int8')
segs, info = model.transcribe('{str(temp_wav)}', language='zh')
srt_lines = []
idx = 1
def fmt(s):
    hrs = int(s // 3600)
    mins = int((s % 3600) // 60)
    secs = int(s % 60)
    msecs = int(round((s - int(s)) * 1000))
    return f"{{hrs:02d}}:{{mins:02d}}:{{secs:02d}},{{msecs:03d}}"

for s in segs:
    clean = (s.text.strip()
             .replace('掩饰', '演示')
             .replace('公单', '工单')
             .replace('供单', '工单')
             .replace('合销', '核销')
             .replace('代售礼', '待受理')
             .replace('实施看板', '实时看板')
             .replace('时时', '实时')
             .replace('岛航蓝', '导航栏')
             .replace('叫大家', '教大家')
             .replace('报休', '报修')
             .replace('支保', '质保'))
    if not clean: continue
    srt_lines.append(f"{{idx}}\\n{{fmt(s.start)}} --> {{fmt(s.end)}}\\n{{clean}}\\n")
    idx += 1

with open('{str(output_srt)}', 'w', encoding='utf-8') as f:
    f.write('\\n'.join(srt_lines) + '\\n')
"""
    whisper_res = subprocess.run([str(VENV_PYTHON), "-c", whisper_script], capture_output=True, text=True)
    if whisper_res.returncode != 0:
        print(f"⚠️ Whisper 提取警告: {whisper_res.stderr}")
        # 保底机制：若 whisper 异常，生成整段单字幕
        output_srt.write_text(f"1\n00:00:00,000 --> 00:00:10,000\n{text}\n", encoding="utf-8")

    print(f"✅ 专属配音与字幕生成完毕！\n  音频: {output_audio}\n  字幕: {output_srt}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output-audio", required=True)
    parser.add_argument("--output-srt", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--ref-audio", default=None, help="参考音频路径")
    parser.add_argument("--ref-text", default=None, help="参考音频文本")
    args = parser.parse_args()

    ref_audio_p = Path(args.ref_audio) if args.ref_audio else None
    synthesize_custom_voice(args.text, Path(args.output_audio), Path(args.output_srt), args.speed, ref_audio_p, args.ref_text)
