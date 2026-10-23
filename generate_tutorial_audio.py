def get_subtitle_font() -> str:
    """根据操作系统选用最优中文字体，避免 Windows/Linux 缺少苹方产生乱码"""
    if sys.platform == 'win32':
        return 'Microsoft YaHei'
    elif sys.platform == 'darwin':
        return 'PingFang SC'
    return 'Noto Sans CJK SC'

#!/usr/bin/env python3
"""
教程视频 AI 配音与字幕生成工具 (基于 Edge-TTS & FFmpeg)
无需任何 API Key，离线/直连微软超逼真自然语音引擎。

使用方法:
  1. 生成配音与字幕:
     python3 video_tools/generate_tutorial_audio.py --script video_tools/sample_asc_tutorial.txt --output video_tools/output/tutorial

  2. 一键合并到录屏视频中（含视频字幕烧录）:
     python3 video_tools/generate_tutorial_audio.py --script video_tools/sample_asc_tutorial.txt --video my_screen_record.mp4 --burn-subtitles --output video_tools/output/final_tutorial.mp4
"""

import argparse
import subprocess
import shutil
import sys
import os
from pathlib import Path

# 常用高质量中文自然语音
VOICES = {
    "xiaoxiao": ("zh-CN-XiaoxiaoNeural", "晓晓（知性亲和女声 · 推荐：SaaS/产品教程首选）"),
    "yunxi": ("zh-CN-YunxiNeural", "云希（阳光活力男声 · 推荐：B站科技数码风）"),
    "yunjian": ("zh-CN-YunjianNeural", "云健（沉稳影视男声 · 推荐：严肃企业培训）"),
    "xiaoyi": ("zh-CN-XiaoyiNeural", "晓伊（温柔解说女声）"),
    "yunxia": ("zh-CN-YunxiaNeural", "云夏（青春少年男声）"),
    "liaoning": ("zh-CN-liaoning-XiaobeiNeural", "东北老妹儿（幽默接地气）"),
    "shaanxi": ("zh-CN-shaanxi-XiaoniNeural", "陕西话（方言特色讲解）"),
}

def check_dependencies():
    """检查 uv / uvx 和 ffmpeg 是否可用"""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        print("⚠️ 提示: 未检测到 ffmpeg，音视频合并功能可能受限。")

def get_edge_tts_cmd():
    if shutil.which("edge-tts"):
        return ["edge-tts"]
    if shutil.which("uvx"):
        return ["uvx", "edge-tts"]
    return [sys.executable, "-m", "edge_tts"]

def generate_tts(text_content: str, output_prefix: Path, voice_id: str, rate: str = "+0%"):
    audio_path = output_prefix.with_suffix(".mp3")
    vtt_path = output_prefix.with_suffix(".vtt")
    srt_path = output_prefix.with_suffix(".srt")

    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    print(f"🎙️ 正在使用配音演员 [{voice_id}] 合成讲解音频...")
    cmd = get_edge_tts_cmd() + [
        "--voice", voice_id,
        "--text", text_content,
        "--rate", rate,
        "--write-media", str(audio_path),
        "--write-subtitles", str(vtt_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ 配音生成失败: {res.stderr}")
        sys.exit(1)

    print(f"✅ 音频生成成功: {audio_path}")

    # 将 VTT 转成通用的 SRT 格式（方便剪映或播放器载入）
    if vtt_path.exists():
        convert_vtt_to_srt(vtt_path, srt_path)
        print(f"✅ SRT 标准字幕: {srt_path}")

    return audio_path, srt_path

def convert_vtt_to_srt(vtt_path: Path, srt_path: Path):
    """将 WebVTT 转换成标准的 SRT 格式"""
    lines = vtt_path.read_text(encoding="utf-8").splitlines()
    srt_lines = []
    counter = 1
    skip_header = True

    for line in lines:
        if skip_header:
            if "-->" in line:
                skip_header = False
            else:
                continue

        if "-->" in line:
            time_line = line.replace(".", ",")
            srt_lines.append(str(counter))
            srt_lines.append(time_line)
            counter += 1
        else:
            srt_lines.append(line)

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

def merge_video_audio(video_path: Path, audio_path: Path, srt_path: Path, output_video: Path, burn_subtitles: bool = True):
    """使用 FFmpeg 将原录屏视频与 AI 生成的配音合并，并可选压制字幕"""
    print(f"🎬 正在将视频 [{video_path.name}] 与配音合成...")
    output_video.parent.mkdir(parents=True, exist_ok=True)

    # 如果需要烧录字幕
    if burn_subtitles and srt_path and srt_path.exists():
        print(f"✨ 正在将标准字幕压制到视频底部 (半透明黑底胶囊质感)...")
        # 转义路径中的特殊字符
        escaped_srt = str(srt_path.resolve()).replace(":", "\\:").replace("'", "\\'")
        # 字幕样式：白色文字、半透明黑底背景框、距底边 28 像素、苹方/思源黑体
        sub_font = get_subtitle_font()
        sub_filter = (
            f"subtitles='{escaped_srt}':force_style="
            f"'Fontname={sub_font},FontSize=10.5,PrimaryColour=&H00FFFFFF,OutlineColour=&H75000000,"
            f"BackColour=&H75000000,BorderStyle=3,Outline=2.5,Shadow=0,MarginV=22'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-vf", sub_filter,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            "-af", "apad",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_video)
        ]
    else:
        # 仅替换音频，极速拷贝
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-af", "apad",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_video)
        ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"🎉 最终教程视频合成完成: {output_video}")
    else:
        print(f"❌ 视频合成失败: {res.stderr}")

def main():
    parser = argparse.ArgumentParser(description="软件教程 AI 配音与字幕自动化生成工具")
    parser.add_argument("--script", "-s", type=str, help="旁白解说文案文本文件路径")
    parser.add_argument("--text", "-t", type=str, help="直接输入的旁白文案字符串")
    parser.add_argument("--voice", "-v", default="xiaoxiao", choices=list(VOICES.keys()), help="选择配音风格 (默认: xiaoxiao)")
    parser.add_argument("--rate", "-r", default="+0%", help="语速调节，如 '+10%', '-5%'")
    parser.add_argument("--output", "-o", default="video_tools/output/tutorial", help="输出文件路径或前缀")
    parser.add_argument("--video", type=str, help="传入 OpenScreen 录屏原始视频路径")
    parser.add_argument("--burn-subtitles", "-b", action="store_true", help="是否直接将字幕压制到视频底部 (苹果风格字幕)")

    args = parser.parse_args()

    if not args.script and not args.text:
        print("请提供台词脚本！例如:")
        print("  python3 video_tools/generate_tutorial_audio.py --script video_tools/sample_asc_tutorial.txt")
        sys.exit(1)

    text_content = ""
    if args.script:
        script_file = Path(args.script)
        if not script_file.exists():
            print(f"❌ 文件不存在: {script_file}")
            sys.exit(1)
        text_content = script_file.read_text(encoding="utf-8").strip()
    else:
        text_content = args.text.strip()

    check_dependencies()

    voice_id, voice_desc = VOICES[args.voice]
    print(f"✨ 已选择声音: {voice_desc}")

    out_prefix = Path(args.output)
    audio_path, srt_path = generate_tts(text_content, out_prefix, voice_id, args.rate)

    if args.video:
        vid_path = Path(args.video)
        if vid_path.exists():
            final_video = out_prefix.with_suffix(".mp4")
            merge_video_audio(vid_path, audio_path, srt_path, final_video, burn_subtitles=args.burn_subtitles)
        else:
            print(f"⚠️ 指定的视频文件未找到: {vid_path}")

    print("\n👉 提示：你也可以直接将生成的 .srt 字幕和 .mp3 音频导入剪映 / Final Cut / Premiere 中直接套用炫酷动画花字！")

if __name__ == "__main__":
    main()
