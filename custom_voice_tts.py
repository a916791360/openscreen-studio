#!/usr/bin/env python3
"""
OpenScreen Studio 专属音色高保真合成与时间轴对齐引擎
- 基于 F5-TTS 内存级自适应神经推理
- 独创【原文原生时间轴对齐 (Verbatim Native Alignment)】：
  杜绝传统 ASR 语音识别带来的同音错别字（如将“工单”识别为“供丹”）与吞字漏字问题，
  100% 忠实还原用户输入的原文，毫秒级音画同步。
- 内置广播级人声母带增强链（Vocal Master Chain）。
"""

import sys
import os
import re
import argparse
import subprocess
from pathlib import Path
import numpy as np

# 动态确保当前虚拟环境 site-packages 在优先搜索路径
BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv_tts"
if VENV_DIR.exists():
    site_packages = list(VENV_DIR.glob("lib/python*/site-packages"))
    if site_packages and str(site_packages[0]) not in sys.path:
        sys.path.insert(0, str(site_packages[0]))

import soundfile as sf
import torch
import torchaudio

# Monkeypatch torchaudio.load / save with soundfile (规避 macOS torchcodec 动态库加载冲突)
def _safe_load_audio(filepath, *args, **kwargs):
    data, sr = sf.read(filepath)
    t = torch.from_numpy(data).float()
    return (t.unsqueeze(0) if t.ndim == 1 else t.t()), sr

def _safe_save_audio(filepath, tensor, sample_rate, *args, **kwargs):
    data = tensor.squeeze().cpu().numpy()
    sf.write(filepath, data, sample_rate)

torchaudio.load = _safe_load_audio
torchaudio.save = _safe_save_audio

from importlib.resources import files
from omegaconf import OmegaConf
from hydra.utils import get_class
from cached_path import cached_path
from f5_tts.infer.utils_infer import load_model, load_vocoder, infer_process, preprocess_ref_audio_text
from f5_tts.model import DiT

CUSTOM_VOICE_DIR = BASE_DIR / "custom_voice"
DEFAULT_REF_AUDIO = CUSTOM_VOICE_DIR / "ref_clip_engineer.wav"
DEFAULT_REF_TEXT = "工程师接单后，移动端会立即收到推送提醒，包括精准的客户地址。"

def get_optimal_device() -> str:
    try:
        if sys.platform == "darwin" and torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"

def format_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msecs = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

def split_script_into_segments(text: str):
    """
    智能将用户文案切分为适合字幕展示的单句/分镜，
    既保留用户手动换行意图，又防止超长单行溢出屏幕。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    segments = []
    for l in lines:
        if len(l) > 32:
            # 依逗号或分号自然断句
            sub = re.split(r'([，,。；;！!？?]+)', l)
            buf = ""
            for p in sub:
                buf += p
                if re.match(r'[，,。；;！!？?]+', p) and len(buf) >= 12:
                    segments.append(buf.strip())
                    buf = ""
            if buf.strip():
                segments.append(buf.strip())
        else:
            segments.append(l)
    return segments

def synthesize_custom_voice(text: str, output_audio: Path, output_srt: Path, speed: float = 1.0, ref_audio: Path = None, ref_text: str = None):
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    temp_wav = output_audio.with_suffix(".raw.wav")
    
    active_ref_audio = ref_audio or DEFAULT_REF_AUDIO
    active_ref_text = ref_text or DEFAULT_REF_TEXT
    device = get_optimal_device()

    print(f"🎙️ [1/3] 正在加载 F5-TTS 专属模型 (设备: {device})...")
    model_cfg = OmegaConf.load(str(files("f5_tts").joinpath("configs/F5TTS_Base.yaml")))
    model_cls = get_class(f"f5_tts.model.{model_cfg.model.backbone}")
    model_arc = model_cfg.model.arch

    ckpt_file = str(cached_path("hf://SWivid/F5-TTS/F5TTS_Base/model_1200000.safetensors"))
    vocoder = load_vocoder(vocoder_name="vocos", is_local=False, local_path="", device=device)
    ema_model = load_model(model_cls, model_arc, ckpt_file, mel_spec_type="vocos", device=device)

    pre_ref_audio, pre_ref_text = preprocess_ref_audio_text(str(active_ref_audio), active_ref_text)

    segments = split_script_into_segments(text)
    print(f"✨ [2/3] 开始逐句精准合成与原生字轨时间轴锚定 (共 {len(segments)} 个分镜字幕)...")

    waves = []
    srt_lines = []
    current_time = 0.0
    target_sr = 24000
    pause_sec = 0.18  # 句间自然呼吸停顿

    for idx, seg_text in enumerate(segments):
        print(f"   [{idx + 1}/{len(segments)}] 正在生成: {seg_text[:24]}...")
        wave, sr, _ = infer_process(
            pre_ref_audio,
            pre_ref_text,
            seg_text,
            ema_model,
            vocoder,
            mel_spec_type="vocos",
            nfe_step=16,
            speed=speed,
            device=device
        )
        target_sr = sr
        dur = len(wave) / target_sr
        start_ts = current_time
        end_ts = current_time + dur

        # 100% 严谨使用用户原始文案，杜绝语音识别错别字！
        srt_lines.append(
            f"{idx + 1}\n{format_timestamp(start_ts)} --> {format_timestamp(end_ts)}\n{seg_text}\n"
        )

        waves.append(wave)
        # 添加自然语句间歇
        pause_samples = np.zeros(int(pause_sec * target_sr), dtype=wave.dtype)
        waves.append(pause_samples)
        current_time = end_ts + pause_sec

    # 拼接完整波形
    final_wave = np.concatenate(waves)
    sf.write(str(temp_wav), final_wave, target_sr)

    # 保存 100% 严谨同步的 SRT 字幕
    output_srt.write_text("\n".join(srt_lines) + "\n", encoding="utf-8")
    print(f"✅ 原生字幕时间轴已对齐 (共 {len(segments)} 条): {output_srt}")

    # [3/3] 广播级人声母带增强链 (消除发闷感、提亮齿音空气感与动态压限)
    print(f"🎵 [3/3] 正在通过广播级人声母带链增强清晰度并压制 MP3...")
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
    if temp_wav.exists():
        temp_wav.unlink()

    print(f"🎉 专属配音成片音频已完成: {output_audio}")

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
