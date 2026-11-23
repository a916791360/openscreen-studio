#!/usr/bin/env python3
# Copyright (c) 2026 杨冉 (https://github.com/a916791360)
# SPDX-License-Identifier: MIT
"""
OpenScreen Studio · 软件教程自动化视频工作台
Copyright (c) 2026 杨冉 (https://github.com/a916791360)
SPDX-License-Identifier: MIT
Hallmark Macrostructure: 05 · Workbench
Tone: Utilitarian / Technical Slate
Anti-AI-slop design: 零塑料渐变 · 严格时间轴字数拟合 · 精密工业级控制台

运行方式:
  python3 video_tools/studio.py
  (访问 http://localhost:8765)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# 引入我们创建的 AI 解说词引擎与大模型配置管理
from ai_script_generator import (
    adapt_script_to_duration,
    load_llm_config,
    save_llm_config,
    test_llm_connection,
    extract_openscreen_beats,
    analyze_telemetry_phases,
    find_matching_openscreen_project,
    list_available_openscreen_projects,
    generate_script,
    compress_script_to_duration,
    compress_text_to_target,
    translate_srt_bilingual,
    build_bilingual_ass,
    align_tts_to_phases,
    generate_sync_check_grid,
    safe_duration,
    CHARS_PER_SECOND
)

PORT = int(os.environ.get("PORT", 8765))
BASE_DIR = Path(__file__).resolve().parent

def get_openscreen_recordings_dir() -> Path:
    """跨平台动态获取 OpenScreen 录屏工程存储目录 (支持 macOS, Windows, Linux)"""
    if sys.platform == 'win32':
        app_data = os.environ.get('APPDATA')
        if app_data:
            p = Path(app_data) / 'openscreen/recordings'
            if p.exists():
                return p
        return Path.home() / 'AppData/Roaming/openscreen/recordings'
    elif sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/openscreen/recordings'
    else:
        xdg_config = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config:
            p = Path(xdg_config) / 'openscreen/recordings'
            if p.exists():
                return p
        return Path.home() / '.config/openscreen/recordings'

def get_subtitle_font() -> str:
    """根据操作系统选用最优中文字体，避免 Windows/Linux 缺少苹方产生乱码"""
    if sys.platform == 'win32':
        return 'Microsoft YaHei'
    elif sys.platform == 'darwin':
        return 'PingFang SC'
    return 'Noto Sans CJK SC'

def get_custom_tts_python() -> str:
    """跨平台寻找专属音色模型运行环境 (优先查找 .venv_tts 或 .venv 虚拟环境，支持 macOS/Linux 和 Windows)"""
    candidates = [
        BASE_DIR / ".venv_tts/bin/python",
        BASE_DIR / ".venv_tts/Scripts/python.exe",
        BASE_DIR / ".venv/bin/python",
        BASE_DIR / ".venv/Scripts/python.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable

def check_custom_tts_available() -> tuple:
    """自检本地专属音色推理环境 (PyTorch + F5-TTS)"""
    py_bin = get_custom_tts_python()
    try:
        res = subprocess.run([py_bin, "-c", "import torch, f5_tts"], capture_output=True, timeout=5)
        if res.returncode != 0:
            return False, "未检测到专属音色深度学习环境 (缺少 PyTorch 或 F5-TTS)。请先运行 'pip install -r requirements-voice.txt'，或直接使用开箱即用的标准音色（如晓晓、云希）。"
        return True, ""
    except Exception as e:
        return False, f"专属音色环境检查异常: {str(e)}"

RECORDINGS_DIR = get_openscreen_recordings_dir()
DOWNLOADS_DIR = Path.home() / "Downloads"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
CUSTOM_VOICE_DIR = BASE_DIR / "custom_voice"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_VOICE_DIR.mkdir(parents=True, exist_ok=True)

def get_all_voices():
    voices = []
    # 动态载入 custom_voice/voices.json
    v_json = CUSTOM_VOICE_DIR / "voices.json"
    if v_json.exists():
        try:
            with open(v_json, "r", encoding="utf-8") as f:
                c_voices = json.load(f)
                for cv in c_voices:
                    cv["type"] = "custom"
                    voices.append(cv)
        except Exception:
            pass

    DEFAULT_VOICES = [
        {"id": "xiaoxiao", "name": "晓晓", "role": "知性亲和女声", "tag": "SaaS / 功能演示", "voice_id": "zh-CN-XiaoxiaoNeural"},
        {"id": "yunxi", "name": "云希", "role": "阳光活力男声", "tag": "技术架构 / 新特性", "voice_id": "zh-CN-YunxiNeural"},
        {"id": "yunjian", "name": "云健", "role": "沉稳专业男声", "tag": "业务规范 / 培训", "voice_id": "zh-CN-YunjianNeural"},
        {"id": "xiaoyi", "name": "晓伊", "role": "温柔讲解女声", "tag": "操作指引 / 客服", "voice_id": "zh-CN-XiaoyiNeural"},
        {"id": "yunxia", "name": "云夏", "role": "清亮青年男声", "tag": "敏捷快闪 / 提纲", "voice_id": "zh-CN-YunxiaNeural"},
        {"id": "liaoning", "name": "小北", "role": "方言老妹儿", "tag": "轻松解说", "voice_id": "zh-CN-liaoning-XiaobeiNeural"},
        {"id": "shaanxi", "name": "小妮", "role": "陕西特色方言", "tag": "特色讲解", "voice_id": "zh-CN-shaanxi-XiaoniNeural"},
    ]
    voices.extend(DEFAULT_VOICES)
    return voices

VOICES = get_all_voices()

HTML_WORKBENCH = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenScreen Studio</title>
  <style>
    :root, [data-theme="dark"] {
      --bg-base: #090b10;
      --bg-surface: #131722;
      --bg-surface-raised: #1a202c;
      --bg-surface-hover: #222a3a;
      --bg-well: #0c0f17;
      --bg-header: #0e121a;

      --text-primary: #f1f5f9;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;

      --border-subtle: rgba(255, 255, 255, 0.07);
      --border-default: rgba(255, 255, 255, 0.12);
      --border-focus: #3b82f6;

      --card-shadow: 0 0 0 1px rgba(255, 255, 255, 0.07), 0 4px 16px rgba(0, 0, 0, 0.4);
      --card-shadow-hover: 0 0 0 1px rgba(255, 255, 255, 0.14), 0 6px 20px rgba(0, 0, 0, 0.5);

      --color-accent: #3b82f6;
      --color-accent-hover: #2563eb;
      --color-accent-subtle: rgba(59, 130, 246, 0.12);
      --color-accent-text: #60a5fa;

      --color-success: #10b981;
      --color-success-subtle: rgba(16, 185, 129, 0.12);
      --color-warning: #f59e0b;
      --color-warning-subtle: rgba(245, 158, 11, 0.12);
      --color-danger: #ef4444;
      --color-danger-subtle: rgba(239, 68, 68, 0.12);

      --font-display: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Segoe UI", Roboto, sans-serif;
      --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
    }

    [data-theme="light"] {
      --bg-base: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-raised: #f1f5f9;
      --bg-surface-hover: #e2e8f0;
      --bg-well: #f8fafc;
      --bg-header: #ffffff;

      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #94a3b8;

      --border-subtle: rgba(0, 0, 0, 0.06);
      --border-default: rgba(0, 0, 0, 0.12);
      --border-focus: #2563eb;

      --card-shadow: 0 0 0 1px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.04);
      --card-shadow-hover: 0 0 0 1px rgba(0, 0, 0, 0.14), 0 4px 12px rgba(0, 0, 0, 0.06);

      --color-accent: #2563eb;
      --color-accent-hover: #1d4ed8;
      --color-accent-subtle: rgba(37, 99, 235, 0.08);
      --color-accent-text: #2563eb;

      --color-success: #059669;
      --color-success-subtle: rgba(5, 150, 105, 0.08);
      --color-warning: #d97706;
      --color-warning-subtle: rgba(217, 119, 6, 0.08);
      --color-danger: #dc2626;
      --color-danger-subtle: rgba(220, 38, 38, 0.08);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: var(--font-display);
      font-size: 13px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }
    .mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-thumb { background: var(--border-default); border-radius: 3px; }

    /* SVG Icons */
    .icon {
      width: 14px;
      height: 14px;
      stroke-width: 1.75;
      stroke: currentColor;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
      flex-shrink: 0;
      display: inline-block;
      vertical-align: -2px;
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      border: 1px solid var(--border-default);
      background: var(--bg-surface-raised);
      color: var(--text-primary);
      cursor: pointer;
      transition-property: transform, background-color, border-color, box-shadow, color;
      transition-duration: 150ms;
      transition-timing-function: ease-out;
      user-select: none;
      outline: none;
    }
    .btn:hover:not(:disabled) {
      background: var(--bg-surface-hover);
      border-color: var(--text-muted);
    }
    .btn:active:not(:disabled) {
      transform: scale(0.96);
    }
    .btn:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
    .btn-sm {
      padding: 4px 8px;
      font-size: 11px;
    }
    .btn-primary {
      background: var(--color-accent);
      color: #ffffff;
      border-color: var(--color-accent);
      font-weight: 600;
      box-shadow: 0 1px 3px rgba(37, 99, 235, 0.3);
    }
    .btn-primary:hover:not(:disabled) {
      background: var(--color-accent-hover);
      border-color: var(--color-accent-hover);
    }
    .btn-subtle {
      background: var(--color-accent-subtle);
      border-color: rgba(59, 130, 246, 0.25);
      color: var(--color-accent-text);
      font-weight: 600;
    }
    .btn-subtle:hover:not(:disabled) {
      background: var(--color-accent);
      color: #ffffff;
      border-color: var(--color-accent);
    }

    /* Concentric Surface Cards */
    .card {
      background: var(--bg-surface);
      border-radius: 12px;
      box-shadow: var(--card-shadow);
      position: relative;
    }
    .card-header {
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-header);
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-top-left-radius: 12px;
      border-top-right-radius: 12px;
    }

    /* Tags & Pills */
    .tag {
      font-family: var(--font-mono);
      font-size: 11px;
      font-variant-numeric: tabular-nums;
      padding: 2px 7px;
      border-radius: 4px;
      background: var(--bg-surface-raised);
      color: var(--text-secondary);
      border: 1px solid var(--border-subtle);
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .tag-active {
      background: var(--color-accent-subtle);
      color: var(--color-accent-text);
      border-color: rgba(59, 130, 246, 0.3);
      font-weight: 600;
    }

    /* Interactive Voice Card */
    .voice-card {
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface-raised);
      transition-property: border-color, background-color, transform;
      transition-duration: 120ms;
      transition-timing-function: ease-out;
      user-select: none;
    }
    .voice-card:hover {
      border-color: var(--border-default);
      background: var(--bg-surface-hover);
    }
    .voice-card:active {
      transform: scale(0.98);
    }
    .voice-card.active {
      border-color: var(--color-accent);
      background: var(--color-accent-subtle);
    }

    /* Audio Play Button (Optically Centered) */
    .play-btn {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      border: 1px solid var(--border-default);
      background: var(--bg-surface);
      color: var(--text-primary);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      outline: none;
      transition-property: transform, background-color, border-color;
      transition-duration: 120ms;
    }
    .play-btn:hover {
      background: var(--color-accent);
      color: #fff;
      border-color: var(--color-accent);
    }
    .play-btn:active {
      transform: scale(0.92);
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .spin { animation: spin 0.8s linear infinite; }
    .play-glyph {
      width: 9px;
      height: 9px;
      fill: currentColor;
      transform: translateX(1px); /* Optical center nudge */
    }

    /* Grid Layout */
    .workbench-grid {
      display: grid;
      grid-template-columns: 460px 1fr;
      gap: 16px;
      max-width: 1400px;
      margin: 0 auto;
      padding: 16px 20px 40px;
    }
    @media (max-width: 1024px) {
      .workbench-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- Top Tool Header -->
  <header style="background: var(--bg-header); border-bottom: 1px solid var(--border-subtle); position: sticky; top: 0; z-index: 100;">
    <div style="max-width: 1400px; margin: 0 auto; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-weight: 700; font-size: 13px; letter-spacing: 0.5px; color: var(--text-primary);">OPENSCREEN STUDIO</span>
        <span class="tag mono tag-active" style="font-size: 10px;">V3.2</span>
        <select id="history-project-select" onchange="loadHistoryProject(this.value)" title="一键回载历史项目快照（还原视频、文案、分镜秒数、打码区间与音色）" style="background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 3px 8px; font-size: 11px; max-width: 240px; outline: none; cursor: pointer;">
          <option value="">📂 历史项目回载 (0)</option>
        </select>
      </div>
      <div style="display: flex; align-items: center; gap: 12px; font-size: 11px; color: var(--text-muted);">
        <button class="btn btn-sm" id="theme-toggle-btn" onclick="toggleTheme()" style="gap: 5px;">
          <span id="theme-icon">
            <svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
          </span>
          <span id="theme-text">浅色模式</span>
        </button>
        <span class="mono">Engine: F5-TTS · Edge-TTS · OpenScreen</span>
        <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--color-success);" title="服务在线"></span>
      </div>
    </div>
  </header>

  <main class="workbench-grid">
    <!-- LEFT COLUMN: Video Monitor & Ingestion -->
    <div style="display: flex; flex-direction: column; gap: 16px;">
      
      <!-- Video Stage Card -->
      <section class="card" style="overflow: hidden;">
        <div class="card-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 600; font-size: 12px; color: var(--text-primary);">录屏预览与运镜</span>
            <span id="video-timer-badge" class="tag mono">00:00.0 / 00:00.0</span>
            <span id="video-motion-tag" class="tag mono tag-active" style="font-size: 10px;">带运镜动效</span>
          </div>
          <button class="btn btn-sm" onclick="triggerFilePicker()">
            <svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <span>导入视频</span>
          </button>
          <input type="file" id="file-input" accept="video/mp4,video/quicktime,video/webm" style="display:none;" onchange="handleFileSelect(this.files)">
        </div>

        <div id="video-stage-wrap" style="background: #000; position: relative; min-height: 240px; display: flex; align-items: center; justify-content: center; outline: 1px solid var(--border-subtle); overflow: hidden;">
          <video id="stage-player" controls style="width: 100%; max-height: 320px; object-fit: contain; outline: none;"></video>
          <div id="blur-select-overlay" style="display: none; position: absolute; inset: 0; z-index: 20; cursor: crosshair; background: rgba(15, 23, 42, 0.22);">
            <div id="blur-select-box" style="display: none; position: absolute; border: 2px dashed #f59e0b; background: rgba(245, 158, 11, 0.25); pointer-events: none;"></div>
            <div class="mono" style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.82); color: #fcd34d; font-size: 11px; padding: 4px 8px; border-radius: 4px; pointer-events: none;">
              按住鼠标左键拖拽框选隐私打码区域（松开即添加，ESC 取消）
            </div>
          </div>
          <div id="drop-overlay" style="display: none; position: absolute; inset: 0; background: rgba(9,11,16,0.92); border: 2px dashed var(--color-accent); align-items: center; justify-content: center; flex-direction: column; gap: 8px;">
            <span style="font-weight: 500; font-size: 13px; color: var(--text-primary);">松开鼠标以载入视频文件</span>
          </div>
        </div>

        <!-- V3.2 Privacy Blur Interval Bar -->
        <div style="padding: 8px 14px; background: var(--bg-surface); border-top: 1px solid var(--border-subtle);">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">🛡️ 区间隐私高斯模糊 (人脸/邮箱脱敏)</span>
            <div style="display: flex; gap: 6px;">
              <button class="btn btn-sm" id="btn-draw-blur" onclick="startBlurBoxDraw()" style="font-size: 10px; padding: 2px 8px;">+ 在画面框选打码</button>
              <button class="btn btn-sm" onclick="addQuickBlurZone()" style="font-size: 10px; padding: 2px 8px;">+ 手动填区间</button>
            </div>
          </div>
          <div id="privacy-blur-list" style="display: flex; flex-direction: column; gap: 4px; margin-top: 6px;">
            <!-- Dynamic blur rules -->
          </div>
        </div>

        <!-- Video Beat Strip -->
        <div style="padding: 12px 14px; background: var(--bg-header); border-top: 1px solid var(--border-subtle);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="mono" style="font-size: 11px; font-weight: 600; color: var(--text-primary);">OpenScreen 运镜与交互节拍：</span>
              <span id="beats-breakdown-text" class="mono" style="font-size: 10px; color: var(--text-secondary);">检测中...</span>
            </div>
            <span id="beats-count-badge" class="tag mono tag-active" style="font-size: 10px;">0 处动作</span>
          </div>

          <!-- Interactive Timeline Track -->
          <div id="beats-timeline-bar" 
               style="height: 28px; background: var(--bg-well); border-radius: 6px; position: relative; overflow: hidden; border: 1px solid var(--border-subtle); cursor: pointer;"
               title="点击时间轴任意位置可跳转播放">
            <div id="timeline-playhead" style="position: absolute; top:0; bottom:0; width: 2px; background: #ef4444; z-index: 10; pointer-events: none; left: 0%; box-shadow: 0 0 6px #ef4444;"></div>
          </div>

          <!-- Interactive Storyboard Phases Track -->
          <div id="phases-storyboard-bar" style="display: flex; gap: 4px; margin-top: 6px; min-height: 24px;" title="分镜阶段条：点击分镜可跳转播放">
            <!-- Dynamic phase blocks -->
          </div>

          <!-- Mini Beat Chips Row -->
          <div id="beats-chips-container" style="display: flex; gap: 6px; overflow-x: auto; margin-top: 8px; padding-bottom: 2px;">
            <!-- Dynamic chips -->
          </div>
        </div>
      </section>

      <!-- Video Library Drawer -->
      <section class="card" style="padding: 12px 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
          <span style="font-weight: 600; font-size: 12px; color: var(--text-primary);">录屏媒体库</span>
          <button class="btn btn-sm" onclick="fetchRecordings()">
            <svg class="icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            <span>刷新</span>
          </button>
        </div>
        <div id="media-library-list" style="max-height: 180px; overflow-y: auto; padding-right: 2px;">
          <!-- Dynamically populated -->
        </div>
      </section>

      <!-- Voice Calibration Rack -->
      <section class="card" style="padding: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <span style="font-weight: 600; font-size: 12px; color: var(--text-primary);">解说音色与语速</span>
          <span class="tag mono" id="speed-meter">4.3 字/秒</span>
        </div>

        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;" id="voice-rack">
          <!-- Dynamically populated -->
        </div>

        <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border-subtle); display: flex; align-items: center; justify-content: space-between;">
          <span style="color: var(--text-secondary); font-size: 12px;">播报语速微调基准：</span>
          <div style="display: flex; align-items: center; gap: 8px;">
            <input type="range" id="rate-slider" min="-20" max="30" step="5" value="0" style="accent-color: var(--color-accent); width: 110px; cursor: pointer;" oninput="updateSpeedMeter(this.value)">
            <span class="mono" id="rate-label" style="font-size: 11px; width: 36px; text-align: right;">0%</span>
          </div>
        </div>
      </section>

    </div>

    <!-- RIGHT COLUMN: AI Script Director & Synthesis Deck -->
    <div style="display: flex; flex-direction: column; gap: 16px;">
      
      <!-- Script Director Console -->
      <section class="card" style="display: flex; flex-direction: column; flex: 1;">
        <div class="card-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 600; font-size: 12px; color: var(--text-primary);">解说文案与分镜</span>
            <span class="tag mono" id="duration-target-pill">时长预算: --s</span>
          </div>
          <span id="fit-status-badge" class="tag" style="background: var(--bg-surface-raised); color: var(--text-muted);">待分析</span>
        </div>

        <!-- Command Bar -->
        <div style="padding: 10px 14px; background: var(--bg-header); border-bottom: 1px solid var(--border-subtle); display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
          <div style="display: flex; align-items: center; gap: 10px;">
            <button class="btn btn-primary" id="btn-adapt-script" onclick="triggerSmartAdaptScript()" disabled style="opacity: 0.45; cursor: not-allowed; font-weight: 600; padding: 7px 16px; font-size: 12px;">
              智能拟合分镜文案
            </button>
            <span id="adapt-hint-badge" class="mono" style="font-size: 11px; color: var(--text-muted);">
              下方输入操作要点后激活
            </span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <button class="btn btn-sm" onclick="openLlmModal()" style="display: flex; align-items: center; gap: 6px;" title="绑定大模型并控制提示词风格与限制">
              <svg class="icon" viewBox="0 0 24 24"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
              <span>模型与提示词设置</span>
              <span id="llm-status-pill" class="tag mono" style="font-size: 10px; padding: 1px 6px;">读取中...</span>
            </button>
          </div>
        </div>

        <!-- Script Editor -->
        <div style="padding: 14px; flex: 1; display: flex; flex-direction: column;">
          <!-- Storyboard & Narration Linkage Monitor Bar -->
          <div id="storyboard-sync-monitor" style="margin-bottom: 12px; background: var(--bg-header); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 10px 12px; display: none;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span class="mono" style="font-size: 11px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
                <span>分镜音画同步状态：</span>
              </span>
              <span id="storyboard-sync-summary" class="tag mono tag-active" style="font-size: 10px;">待润色拟合</span>
            </div>
            <div id="storyboard-phase-cards" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px;">
              <!-- Dynamic Cards -->
            </div>
          </div>

          <textarea id="script-textarea" 
                    placeholder="在此输入本段视频的操作要点草稿或步骤总结...&#10;例如：在左侧进入工单管理，点击新建工单，输入报修设备与故障现象，指定派发给张工并提交...&#10;&#10;输入后点击上方「智能拟合分镜文案」，系统将根据当前视频的运镜节奏与物理时长，自动生成音画严密卡点的分段解说词。"
                    style="flex: 1; min-height: 280px; width: 100%; background: var(--bg-well); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 12px 14px; font-size: 13px; line-height: 1.75; color: var(--text-primary); resize: vertical; outline: none; font-family: var(--font-display);"
                    oninput="handleScriptInput()"></textarea>

          <!-- Timeline Budget Monitor Bar -->
          <div style="margin-top: 12px; display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--bg-header); border-radius: 8px; border: 1px solid var(--border-subtle); flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; gap: 14px; font-size: 11px;" class="mono">
              <span id="char-count-text">字数: 0 字</span>
              <span id="speech-sec-text">朗读预估: 0.0s</span>
              <span id="delta-sec-text">时间偏差: 0.0s</span>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
              <div style="display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary);">
                <span>字幕字号:</span>
                <select id="sub-fontsize-select" style="background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 4px; padding: 2px 6px; font-size: 11px; outline: none; cursor: pointer;">
                  <option value="9.5">微缩 (9.5pt)</option>
                  <option value="10.5" selected>标准 (10.5pt 推荐)</option>
                  <option value="12">放大 (12.0pt)</option>
                </select>
              </div>
              <label style="display: flex; align-items: center; gap: 6px; font-size: 11px; cursor: pointer; user-select: none; color: var(--text-primary);" title="若音频时长超出视频，末尾画面自动静止定格，保证讲解完整播完，绝不截断讲话">
                <input type="checkbox" id="hold-last-frame-toggle" checked style="accent-color: var(--color-accent);">
                <span>画面定格保底 (防语音截断)</span>
              </label>
              <label style="display: flex; align-items: center; gap: 6px; font-size: 11px; cursor: pointer; user-select: none; color: var(--text-primary);">
                <input type="checkbox" id="burn-sub-toggle" checked style="accent-color: var(--color-accent);">
                <span>压制字幕</span>
              </label>
              <label style="display: flex; align-items: center; gap: 6px; font-size: 11px; cursor: pointer; user-select: none; color: var(--text-primary);" title="开启后将自动调用已绑定的 AI 大模型，将同步字幕翻译为双语对照字幕">
                <input type="checkbox" id="bilingual-sub-toggle" onchange="handleBilingualToggle()" style="accent-color: var(--color-accent);">
                <span>双语字幕</span>
              </label>
              <div id="bilingual-options-wrap" style="display: none; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary);">
                <select id="bilingual-lang-select" onchange="saveBilingualPrefs()" title="选择副字幕目标语言" style="background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 4px; padding: 2px 6px; font-size: 11px; outline: none; cursor: pointer;">
                  <option value="English">英语 (English)</option>
                  <option value="Japanese">日语 (日本語)</option>
                  <option value="Korean">韩语 (한국어)</option>
                  <option value="Traditional Chinese">繁体中文</option>
                  <option value="Spanish">西班牙语 (Español)</option>
                  <option value="French">法语 (Français)</option>
                  <option value="German">德语 (Deutsch)</option>
                  <option value="custom">自定义语言...</option>
                </select>
                <input type="text" id="bilingual-custom-lang" placeholder="如：泰语 / 印尼语" onchange="saveBilingualPrefs()" style="display: none; width: 108px; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 4px; padding: 2px 6px; font-size: 11px; outline: none;">
                <select id="bilingual-order-select" onchange="saveBilingualPrefs()" title="双语上下排布顺序" style="background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 4px; padding: 2px 6px; font-size: 11px; outline: none; cursor: pointer;">
                  <option value="orig_top">上原文 · 下译文</option>
                  <option value="trans_top">上译文 · 下原文</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        <!-- Master Synthesis Deck -->
        <div style="padding: 14px; border-top: 1px solid var(--border-subtle); background: var(--bg-header); border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;">
          <button id="render-master-btn" class="btn btn-primary" style="width: 100%; padding: 11px; font-size: 13px;" onclick="startMasterSynthesis()">
            导出成片 (渲染视频 + AI配音 + 同步字幕)
          </button>
        </div>
      </section>

      <!-- Synthesis Result Drawer -->
      <section id="result-deck" class="card" style="display: none; padding: 16px; border: 1px solid var(--color-success);">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="color: var(--color-success); font-weight: 700; font-size: 13px;">渲染完成</span>
            <span class="mono" id="result-filename-badge" style="font-size: 11px; color: var(--text-secondary);"></span>
            <span class="tag mono" id="result-bilingual-badge" style="display: none; font-size: 10px;"></span>
          </div>
          <div style="display: flex; gap: 8px;">
            <a id="btn-dl-srt" href="#" download class="btn btn-sm">下载字幕 (SRT)</a>
            <a id="btn-dl-mp3" href="#" download class="btn btn-sm">下载音频 (MP3)</a>
            <a id="btn-dl-video" href="#" download class="btn btn-sm btn-primary">下载成片 (MP4)</a>
          </div>
        </div>
        <video id="final-playback-monitor" controls style="width: 100%; max-height: 340px; background: #000; border-radius: 8px; outline: none;"></video>

        <!-- V3.2 Export Sync Self-Check Report & Verification Grid -->
        <div id="sync-check-report" style="display: none; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border-subtle);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
            <span style="font-weight: 700; font-size: 12px; color: var(--text-primary);">🔍 导出音画卡点自检报告 & 分镜九宫格</span>
            <span id="sync-check-summary" class="tag mono tag-active" style="font-size: 10px;">全部达标</span>
          </div>
          <div id="sync-check-warnings" style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;"></div>
          <div id="sync-check-grid-wrap" style="display: none;">
            <a id="sync-check-grid-link" href="#" target="_blank" title="点击新窗口查看大图核验每一帧字幕">
              <img id="sync-check-grid-img" src="" alt="分镜卡点自检九宫格" style="width: 100%; border-radius: 8px; border: 1px solid var(--border-default); cursor: zoom-in;">
            </a>
          </div>
        </div>
      </section>

    </div>
  </main>

  <!-- LLM & Prompt Control Modal -->
  <div id="llm-modal" style="position: fixed; inset: 0; background: rgba(0,0,0,0.72); backdrop-filter: blur(5px); display: none; z-index: 999; align-items: center; justify-content: center; padding: 20px;">
    <div class="card" style="width: 660px; max-width: 100%; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 16px 50px rgba(0,0,0,0.65); border: 1px solid var(--border-focus);">
      
      <!-- Modal Header -->
      <div class="card-header" style="padding: 12px 18px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <svg class="icon" viewBox="0 0 24 24"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
          <span style="font-weight: 700; font-size: 13px; color: var(--text-primary);">模型与提示词设置</span>
        </div>
        <button class="btn btn-sm" onclick="closeLlmModal()" style="padding: 2px 8px; font-size: 12px;">✕</button>
      </div>

      <!-- Modal Body -->
      <div style="padding: 16px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px;">
        
        <!-- Section 1: Provider & Credentials -->
        <div style="background: var(--bg-header); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 12px 14px;">
          <div style="font-weight: 600; font-size: 12px; color: var(--text-primary); margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
            <span>1. 模型服务商与 API Key</span>
            <span class="mono" style="font-size: 10px; color: var(--text-muted);">兼容标准 OpenAI 协议</span>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div>
              <label style="display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">服务商预设：</label>
              <select id="llm-provider-select" onchange="handleProviderChange(this.value)" style="width: 100%; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 6px 10px; font-size: 12px; outline: none; cursor: pointer;">
                <option value="deepseek">DeepSeek (推荐 · 快速高质)</option>
                <option value="openai">OpenAI (GPT-4o / GPT-4o-mini)</option>
                <option value="zhipu">智谱 AI (GLM-4 / GLM-5)</option>
                <option value="siliconflow">硅基流动 SiliconFlow</option>
                <option value="moonshot">月之暗面 Kimi</option>
                <option value="qwen">阿里通义千问</option>
                <option value="custom">本地 Ollama / 自定义代理接口</option>
              </select>
            </div>
            <div>
              <label style="display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">模型名称 (Model)：</label>
              <input type="text" id="llm-model-input" placeholder="例如: glm-5.3-flash" style="width: 100%; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 6px 10px; font-size: 12px; outline: none;">
            </div>
          </div>

          <div style="margin-bottom: 10px;">
            <label style="display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">接口地址 (Base URL)：</label>
            <input type="text" id="llm-url-input" placeholder="https://api.deepseek.com/v1" style="width: 100%; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 6px 10px; font-size: 12px; outline: none;">
          </div>

          <div style="margin-bottom: 10px;">
            <label style="display: block; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">API 密钥 (API Key)：</label>
            <div style="display: flex; gap: 8px;">
              <input type="password" id="llm-key-input" placeholder="sk-..." style="flex: 1; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 6px 10px; font-size: 12px; outline: none; font-family: var(--font-mono);">
              <button class="btn btn-sm" type="button" onclick="toggleKeyVisibility()" style="padding: 0 10px;" title="显示/隐藏密钥">
                <svg class="icon" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 8px; flex-wrap: wrap; gap: 6px;">
            <button class="btn btn-sm" id="btn-test-llm" type="button" onclick="testLlmConn()">
              测试连通性
            </button>
            <span id="test-conn-msg" class="mono" style="font-size: 11px;"></span>
          </div>
        </div>

        <!-- Section 2: System Role & Master Prompt -->
        <div style="background: var(--bg-header); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 12px 14px;">
          <div style="font-weight: 600; font-size: 12px; color: var(--text-primary); margin-bottom: 6px;">
            2. 系统人设与主提示词 (System Directive)
          </div>
          <textarea id="llm-sys-prompt" style="width: 100%; min-height: 60px; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 8px 10px; font-size: 12px; line-height: 1.5; outline: none; resize: vertical;"></textarea>
        </div>

        <!-- Section 3: Style Directives & Constraints -->
        <div style="background: var(--bg-header); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 12px 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 600; font-size: 12px; color: var(--text-primary);">3. 文案风格与润色限制控制 (Style & Constraints)</span>
            <span style="font-size: 10px; color: var(--text-muted);">点击快捷注入规则</span>
          </div>

          <!-- Quick Tag Pills -->
          <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px;">
            <button class="btn btn-sm" type="button" onclick="appendStyleTag('口语自然流利，像同事在身边指引讲解')" style="font-size: 10px; padding: 2px 8px;">自然口语化</button>
            <button class="btn btn-sm" type="button" onclick="appendStyleTag('步骤明确清晰，避免歧义，小白也能看懂')" style="font-size: 10px; padding: 2px 8px;">清晰易懂</button>
            <button class="btn btn-sm" type="button" onclick="appendStyleTag('剔除大话套话，聚焦干练操作步骤')" style="font-size: 10px; padding: 2px 8px;">干练紧凑</button>
            <button class="btn btn-sm" type="button" onclick="appendStyleTag('用词规范标准，适合企业交付与培训')" style="font-size: 10px; padding: 2px 8px;">商务规范</button>
            <button class="btn btn-sm" type="button" onclick="appendStyleTag('100% 严格依照真实操作，严禁虚构未提及的功能')" style="font-size: 10px; padding: 2px 8px;">严禁虚构</button>
            <button class="btn btn-sm" type="button" onclick="appendStyleTag('去掉机械生硬的播音腔与公文腔调')" style="font-size: 10px; padding: 2px 8px;">去播音腔</button>
          </div>

          <textarea id="llm-style-prompt" style="width: 100%; min-height: 80px; background: var(--bg-well); border: 1px solid var(--border-default); color: var(--text-primary); border-radius: 6px; padding: 8px 10px; font-size: 12px; line-height: 1.5; outline: none; resize: vertical;"></textarea>
        </div>

      </div>

      <!-- Modal Footer -->
      <div class="card-header" style="border-top: 1px solid var(--border-subtle); border-bottom: none; border-radius: 0; padding: 12px 18px; justify-content: flex-end; gap: 10px;">
        <button class="btn" onclick="closeLlmModal()">取消</button>
        <button class="btn btn-primary" onclick="saveLlmSettings()">保存配置</button>
      </div>

    </div>
  </div>

  <audio id="voice-previewer" style="display: none;"></audio>

  <script>

    const PROVIDER_PRESETS = {
      deepseek: { url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
      openai: { url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
      zhipu: { url: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
      siliconflow: { url: "https://api.siliconflow.cn/v1", model: "deepseek-ai/DeepSeek-V3" },
      moonshot: { url: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
      qwen: { url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-turbo" },
      custom: { url: "http://localhost:11434/v1", model: "llama3" }
    };

    let activeVideoPath = null;
    let activeDuration = 42.5;
    let activeVoice = "xiaoxiao";
    let activeBeats = [];
    let voicesList = [];
    let historyProjects = [];
    let privacyBlurs = [];

    // 初始化
    async function initWorkbench() {
      initTheme();
      initBilingualPrefs();
      setupDragDrop();
      setupBlurBoxDrawing();
      await loadLlmConfig();
      await loadVoices();
      await fetchRecordings();
      await fetchHistoryProjects();
    }

    // ============ V3.2 历史项目一键回载 ============
    async function fetchHistoryProjects() {
      try {
        const res = await fetch('/api/projects');
        const data = await res.json();
        historyProjects = data.projects || [];
        const sel = document.getElementById('history-project-select');
        if (!sel) return;
        sel.innerHTML = `<option value="">📂 历史项目回载 (${historyProjects.length})</option>` +
          historyProjects.map((p, idx) => {
            const label = `${(p.createdAt || '').slice(5, 16)} · ${p.videoName || '未命名'} (${(p.phases || []).length}镜)`;
            return `<option value="${idx}">${label}</option>`;
          }).join('');
      } catch (e) {}
    }

    async function loadHistoryProject(idxStr) {
      if (idxStr === '') return;
      const proj = historyProjects[parseInt(idxStr, 10)];
      if (!proj) return;
      if (proj.videoPath) {
        await selectVideo(proj.videoPath, proj.videoName || '历史项目视频', true);
      }
      if (Array.isArray(proj.phases) && proj.phases.length > 0) {
        window.activePhases = proj.phases;
        renderStoryboardPhasesBar(window.activePhases, activeDuration);
      }
      if (proj.script) {
        const ta = document.getElementById('script-textarea');
        if (ta) {
          ta.value = proj.script;
          handleScriptInput();
        }
      }
      if (proj.voiceKey) {
        selectVoice(proj.voiceKey);
      }
      if (Array.isArray(proj.privacyBlurs)) {
        privacyBlurs = JSON.parse(JSON.stringify(proj.privacyBlurs));
        renderPrivacyBlurList();
      }
      if (proj.finalVideoUrl) {
        const deck = document.getElementById('result-deck');
        const player = document.getElementById('final-playback-monitor');
        const badge = document.getElementById('result-filename-badge');
        if (deck && player) {
          deck.style.display = 'block';
          player.src = proj.finalVideoUrl;
          if (badge) badge.innerText = proj.videoName + ' (历史回载)';
          document.getElementById('btn-dl-video').href = proj.finalVideoUrl;
          document.getElementById('btn-dl-mp3').href = proj.audioUrl || '#';
          document.getElementById('btn-dl-srt').href = proj.srtUrl || '#';
          renderSyncCheckReport(proj.phaseMetrics || [], proj.gridUrl || '');
        }
      }
    }

    // ============ V3.2 区间隐私高斯模糊 ============
    function setupBlurBoxDrawing() {
      const overlay = document.getElementById('blur-select-overlay');
      const box = document.getElementById('blur-select-box');
      if (!overlay || !box) return;
      let drawing = false, startX = 0, startY = 0;

      overlay.addEventListener('mousedown', (e) => {
        const rect = overlay.getBoundingClientRect();
        drawing = true;
        startX = e.clientX - rect.left;
        startY = e.clientY - rect.top;
        box.style.display = 'block';
        box.style.left = startX + 'px';
        box.style.top = startY + 'px';
        box.style.width = '0px';
        box.style.height = '0px';
      });

      overlay.addEventListener('mousemove', (e) => {
        if (!drawing) return;
        const rect = overlay.getBoundingClientRect();
        const curX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
        const curY = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
        box.style.left = Math.min(startX, curX) + 'px';
        box.style.top = Math.min(startY, curY) + 'px';
        box.style.width = Math.abs(curX - startX) + 'px';
        box.style.height = Math.abs(curY - startY) + 'px';
      });

      overlay.addEventListener('mouseup', (e) => {
        if (!drawing) return;
        drawing = false;
        const video = document.getElementById('stage-player');
        const vRect = video.getBoundingClientRect();
        const bRect = box.getBoundingClientRect();
        overlay.style.display = 'none';
        box.style.display = 'none';
        if (bRect.width < 8 || bRect.height < 8 || vRect.width < 10) return;

        // 换算为视频画面归一化坐标 (0~1)
        const nx = Math.max(0, Math.min(0.95, (bRect.left - vRect.left) / vRect.width));
        const ny = Math.max(0, Math.min(0.95, (bRect.top - vRect.top) / vRect.height));
        const nw = Math.max(0.04, Math.min(1 - nx, bRect.width / vRect.width));
        const nh = Math.max(0.04, Math.min(1 - ny, bRect.height / vRect.height));
        const curT = video ? Number((video.currentTime || 0).toFixed(1)) : 0;
        const endT = Number(Math.min(activeDuration || (curT + 10), curT + 10).toFixed(1));
        privacyBlurs.push({
          start: curT, end: endT,
          x: Number(nx.toFixed(3)), y: Number(ny.toFixed(3)),
          w: Number(nw.toFixed(3)), h: Number(nh.toFixed(3))
        });
        renderPrivacyBlurList();
      });

      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.style.display === 'block') {
          drawing = false;
          overlay.style.display = 'none';
          box.style.display = 'none';
        }
      });
    }

    function startBlurBoxDraw() {
      const video = document.getElementById('stage-player');
      if (video && !video.paused) video.pause();
      const overlay = document.getElementById('blur-select-overlay');
      if (overlay) overlay.style.display = 'block';
    }

    function addQuickBlurZone() {
      const video = document.getElementById('stage-player');
      const curT = video ? Number((video.currentTime || 0).toFixed(1)) : 0;
      const endT = Number(Math.min(activeDuration || (curT + 15), curT + 15).toFixed(1));
      privacyBlurs.push({ start: curT, end: endT, x: 0.35, y: 0.25, w: 0.30, h: 0.35 });
      renderPrivacyBlurList();
    }

    function updateBlurRule(idx, field, val) {
      if (!privacyBlurs[idx]) return;
      const num = parseFloat(val);
      if (!isNaN(num)) privacyBlurs[idx][field] = num;
    }

    function removeBlurRule(idx) {
      privacyBlurs.splice(idx, 1);
      renderPrivacyBlurList();
    }

    function renderPrivacyBlurList() {
      const box = document.getElementById('privacy-blur-list');
      if (!box) return;
      if (!privacyBlurs.length) {
        box.innerHTML = `<div style="font-size: 10px; color: var(--text-muted);">未配置打码区间（如需对人脸或敏感信息脱敏，可点击右侧按钮在播放器上框选）</div>`;
        return;
      }
      box.innerHTML = privacyBlurs.map((b, i) => `
        <div class="mono" style="display: flex; align-items: center; gap: 6px; font-size: 10px; background: var(--bg-well); padding: 4px 8px; border-radius: 5px; border: 1px solid var(--border-subtle); flex-wrap: wrap;">
          <span style="color: var(--color-warning); font-weight: 700;">#${i+1}</span>
          <span>起</span><input type="number" step="0.5" value="${b.start}" onchange="updateBlurRule(${i},'start',this.value)" style="width:46px;background:var(--bg-surface);border:1px solid var(--border-default);color:var(--text-primary);border-radius:3px;padding:1px 3px;font-size:10px;">
          <span>止</span><input type="number" step="0.5" value="${b.end}" onchange="updateBlurRule(${i},'end',this.value)" style="width:46px;background:var(--bg-surface);border:1px solid var(--border-default);color:var(--text-primary);border-radius:3px;padding:1px 3px;font-size:10px;">
          <span style="color:var(--text-muted);">区域(${Math.round(b.x*100)}%,${Math.round(b.y*100)}% · ${Math.round(b.w*100)}×${Math.round(b.h*100)}%)</span>
          <button class="btn btn-sm" onclick="removeBlurRule(${i})" style="margin-left:auto;padding:1px 5px;font-size:10px;color:var(--color-danger);">删</button>
        </div>
      `).join('');
    }

    // ============ V3.2 导出音画卡点自检报告 & 九宫格 ============
    function renderSyncCheckReport(metrics, gridUrl) {
      const wrap = document.getElementById('sync-check-report');
      const sumEl = document.getElementById('sync-check-summary');
      const warnEl = document.getElementById('sync-check-warnings');
      const gridWrap = document.getElementById('sync-check-grid-wrap');
      const gridImg = document.getElementById('sync-check-grid-img');
      const gridLink = document.getElementById('sync-check-grid-link');
      if (!wrap) return;
      if ((!metrics || !metrics.length) && !gridUrl) {
        wrap.style.display = 'none';
        return;
      }
      wrap.style.display = 'block';
      const warns = (metrics || []).filter(m => m.warn);
      if (sumEl) {
        if (warns.length > 0) {
          sumEl.innerText = `共 ${metrics.length} 镜 · ${warns.length} 镜偏长已自动微加速 (>1.15x)`;
          sumEl.style.background = 'var(--color-warning-subtle)';
          sumEl.style.color = 'var(--color-warning)';
        } else {
          sumEl.innerText = `共 ${metrics.length} 镜 · 全部自然语速精准卡点`;
          sumEl.style.background = '';
          sumEl.style.color = '';
        }
      }
      if (warnEl) {
        warnEl.innerHTML = (metrics || []).map(m => {
          const col = m.warn ? 'var(--color-warning)' : 'var(--text-secondary)';
          const bg = m.warn ? 'var(--color-warning-subtle)' : 'var(--bg-well)';
          const tip = m.warn ? `偏长(${m.speed}x)` : (m.waited_sec > 0.2 ? `等画面+${m.waited_sec}s` : '1.0x');
          return `<span class="mono" style="font-size:10px;padding:2px 6px;border-radius:4px;background:${bg};color:${col};border:1px solid var(--border-subtle);" title="${m.sample_text || ''}">P${m.phase} ${m.actual_start}s · ${tip}</span>`;
        }).join('');
      }
      if (gridWrap && gridImg && gridLink) {
        if (gridUrl) {
          gridWrap.style.display = 'block';
          gridImg.src = gridUrl;
          gridLink.href = gridUrl;
        } else {
          gridWrap.style.display = 'none';
        }
      }
    }

    function initBilingualPrefs() {
      try {
        const enabled = localStorage.getItem('openscreen_bilingual_enabled') === '1';
        const lang = localStorage.getItem('openscreen_bilingual_lang') || 'English';
        const customLang = localStorage.getItem('openscreen_bilingual_custom_lang') || '';
        const order = localStorage.getItem('openscreen_bilingual_order') || 'orig_top';

        const toggle = document.getElementById('bilingual-sub-toggle');
        const langSel = document.getElementById('bilingual-lang-select');
        const customIn = document.getElementById('bilingual-custom-lang');
        const orderSel = document.getElementById('bilingual-order-select');

        if (toggle) toggle.checked = enabled;
        if (langSel) langSel.value = Array.from(langSel.options).some(o => o.value === lang) ? lang : 'English';
        if (customIn) customIn.value = customLang;
        if (orderSel) orderSel.value = (order === 'trans_top') ? 'trans_top' : 'orig_top';
        syncBilingualVisibility();
      } catch (e) {}
    }

    function syncBilingualVisibility() {
      const toggle = document.getElementById('bilingual-sub-toggle');
      const wrap = document.getElementById('bilingual-options-wrap');
      const langSel = document.getElementById('bilingual-lang-select');
      const customIn = document.getElementById('bilingual-custom-lang');
      if (wrap && toggle) {
        wrap.style.display = toggle.checked ? 'flex' : 'none';
      }
      if (customIn && langSel) {
        customIn.style.display = (toggle && toggle.checked && langSel.value === 'custom') ? 'inline-block' : 'none';
      }
    }

    function handleBilingualToggle() {
      syncBilingualVisibility();
      saveBilingualPrefs();
    }

    function saveBilingualPrefs() {
      syncBilingualVisibility();
      try {
        const toggle = document.getElementById('bilingual-sub-toggle');
        const langSel = document.getElementById('bilingual-lang-select');
        const customIn = document.getElementById('bilingual-custom-lang');
        const orderSel = document.getElementById('bilingual-order-select');
        if (toggle) localStorage.setItem('openscreen_bilingual_enabled', toggle.checked ? '1' : '0');
        if (langSel) localStorage.setItem('openscreen_bilingual_lang', langSel.value);
        if (customIn) localStorage.setItem('openscreen_bilingual_custom_lang', customIn.value.trim());
        if (orderSel) localStorage.setItem('openscreen_bilingual_order', orderSel.value);
      } catch (e) {}
    }

    function initTheme() {
      let saved = 'dark';
      try { saved = localStorage.getItem('studio_theme') || 'dark'; } catch (e) {}
      document.documentElement.setAttribute('data-theme', saved);
      updateThemeBtn(saved);
    }

    // better-ui: Suppress transitions on theme switch
    function toggleTheme() {
      const cur = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = cur === 'dark' ? 'light' : 'dark';

      const style = document.createElement('style');
      style.textContent = '*,*::before,*::after{transition:none !important}';
      document.head.appendChild(style);

      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('studio_theme', next); } catch (e) {}
      updateThemeBtn(next);

      const _reflow = document.body.offsetHeight;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => style.remove());
      });
    }

    function updateThemeBtn(theme) {
      const icon = document.getElementById('theme-icon');
      const text = document.getElementById('theme-text');
      if (theme === 'light') {
        if (icon) icon.innerHTML = '<svg class="icon" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
        if (text) text.innerText = '深色模式';
      } else {
        if (icon) icon.innerHTML = '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
        if (text) text.innerText = '浅色模式';
      }
    }

    // 拖拽支持
    function setupDragDrop() {
      const overlay = document.getElementById('drop-overlay');

      window.addEventListener('dragover', (e) => {
        e.preventDefault();
        overlay.style.display = 'flex';
      });
      window.addEventListener('dragleave', (e) => {
        if (e.clientX <= 0 || e.clientY <= 0) overlay.style.display = 'none';
      });
      window.addEventListener('drop', (e) => {
        e.preventDefault();
        overlay.style.display = 'none';
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          uploadLocalFile(e.dataTransfer.files[0]);
        }
      });
    }

    function triggerFilePicker() {
      document.getElementById('file-input').click();
    }

    function handleFileSelect(files) {
      if (files && files.length > 0) uploadLocalFile(files[0]);
    }

    async function uploadLocalFile(file) {
      const btn = document.querySelector('button[onclick="triggerFilePicker()"]');
      const originalText = btn.innerHTML;
      btn.innerHTML = '<span>载入中...</span>';
      try {
        const res = await fetch('/api/upload?filename=' + encodeURIComponent(file.name), {
          method: 'POST',
          body: file
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error);
        await fetchRecordings();
        selectVideo(data.path, data.duration);
      } catch (err) {
        alert('导入失败: ' + err.message);
      } finally {
        btn.innerHTML = originalText;
      }
    }

    function escapeHtml(str) {
      return String(str || '').replace(/[&<>"']/g, s => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[s]));
    }

    async function loadVoices() {
      try {
        const res = await fetch('/api/voices');
        voicesList = await res.json();
      } catch (e) {
        voicesList = [];
      }

      // 读取本地持久化的音色偏好，若无则优先选中第一个有效音色
      let savedVoice = null;
      try { savedVoice = localStorage.getItem('openscreen_active_voice'); } catch (e) {}
      if (savedVoice && voicesList.some(v => v.id === savedVoice)) {
        activeVoice = savedVoice;
      } else if (!activeVoice || !voicesList.some(v => v.id === activeVoice)) {
        activeVoice = voicesList[0] ? voicesList[0].id : "xiaoxiao";
      }

      const rack = document.getElementById('voice-rack');
      if (!rack) return;
      rack.innerHTML = voicesList.map(v => {
        const safeId = escapeHtml(v.id);
        return `
        <div class="voice-card ${v.id === activeVoice ? 'active' : ''}"
             onclick="selectVoice('${safeId}')" data-voice="${safeId}">
          <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
              <div style="font-weight: 600; font-size: 12px; color: var(--text-primary); display: flex; align-items: center; gap: 4px;">
                ${escapeHtml(v.name)}
                ${v.type === 'custom' ? '<span class="tag mono" style="font-size: 9px; padding: 1px 4px; background: var(--color-accent); color: white; border-radius: 4px;">私有克隆</span>' : ''}
              </div>
              <div class="mono" style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">${escapeHtml(v.role)}</div>
            </div>
            <button class="play-btn" onclick="previewVoiceAudio(event, '${safeId}')" title="试听声音">
              <svg class="play-glyph" viewBox="0 0 16 16"><polygon points="4,2 14,8 4,14"/></svg>
            </button>
          </div>
          <div style="margin-top: 4px; font-size: 10px; color: var(--text-secondary);">${escapeHtml(v.tag)}</div>
        </div>
      `;
      }).join('');
    }

    function selectVoice(id) {
      activeVoice = id;
      try { localStorage.setItem('openscreen_active_voice', id); } catch(e){}
      document.querySelectorAll('#voice-rack .voice-card').forEach(el => {
        if (el.dataset.voice === id) {
          el.classList.add('active');
        } else {
          el.classList.remove('active');
        }
      });
    }

    let _activeAudio = null;
    let _activePlayBtn = null;
    let _previewReqId = 0;

    function _resetPlayBtn(b) {
      if (!b) return;
      b.innerHTML = '<svg class="play-glyph" viewBox="0 0 16 16"><polygon points="4,2 14,8 4,14"/></svg>';
      b.style.opacity = '1';
    }

    async function previewVoiceAudio(e, voiceId) {
      e.stopPropagation();
      const btn = e.currentTarget;

      // 如果当前正在播放同一个，再次点击则暂停并取消挂起请求
      if (_activePlayBtn === btn && _activeAudio && !_activeAudio.paused) {
        _previewReqId++;
        _activeAudio.pause();
        _resetPlayBtn(btn);
        _activeAudio = null;
        _activePlayBtn = null;
        return;
      }

      // 停止之前的播放或挂起中的请求，并立即恢复旧按钮状态
      const reqId = ++_previewReqId;
      if (_activeAudio) {
        _activeAudio.pause();
        _activeAudio = null;
      }
      if (_activePlayBtn && _activePlayBtn !== btn) {
        _resetPlayBtn(_activePlayBtn);
      }

      _activePlayBtn = btn;
      btn.style.opacity = '0.6';
      btn.innerHTML = '<svg class="icon spin" viewBox="0 0 24 24" style="width: 12px; height: 12px;"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4"/></svg>';

      try {
        const res = await fetch('/api/preview-voice?voice=' + encodeURIComponent(voiceId));
        if (reqId !== _previewReqId) return;
        const data = await res.json();
        if (reqId !== _previewReqId) return;
        if (!data.url) throw new Error(data.error || '未获取到试听音频');

        const audio = new Audio(data.url);
        _activeAudio = audio;

        audio.onended = () => {
          if (reqId !== _previewReqId) return;
          _resetPlayBtn(btn);
          _activeAudio = null;
          _activePlayBtn = null;
        };

        audio.onerror = (err) => {
          if (reqId !== _previewReqId) return;
          console.error('试听加载失败:', err);
          _resetPlayBtn(btn);
          _activeAudio = null;
          _activePlayBtn = null;
        };

        await audio.play();
        if (reqId !== _previewReqId) {
          audio.pause();
          return;
        }
        btn.style.opacity = '1';
        btn.innerHTML = '<svg viewBox="0 0 16 16" style="width: 10px; height: 10px; fill: currentColor;"><rect x="3" y="2" width="3.5" height="12"/><rect x="9.5" y="2" width="3.5" height="12"/></svg>';
      } catch (err) {
        if (reqId !== _previewReqId) return;
        console.error('试听异常:', err);
        _resetPlayBtn(btn);
        _activeAudio = null;
        _activePlayBtn = null;
        alert('试听加载失败: ' + err.message);
      }
    }

    async function fetchRecordings() {
      const listEl = document.getElementById('media-library-list');
      try {
        const res = await fetch('/api/recordings');
        const items = await res.json();
        if (items.length === 0) {
          listEl.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 12px;">暂无视频。可点击上方按钮导入。</div>';
          return;
        }

        listEl.innerHTML = items.map((item, idx) => `
          <div class="card" data-path="${item.path}" style="padding: 8px 10px; margin-bottom: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; border: 1px solid ${item.path === activeVideoPath ? 'var(--color-accent)' : 'var(--border-subtle)'}; background: ${item.path === activeVideoPath ? 'var(--color-accent-subtle)' : 'var(--bg-surface-raised)'}; transition: transform 120ms ease-out;"
               onclick="selectVideo('${item.path}', ${item.duration}, ${item.isExported})">
            <div style="overflow: hidden; padding-right: 8px;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span style="font-weight: 600; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; color: var(--text-primary);">${item.name}</span>
                ${item.isExported ? '<span class="tag tag-active" style="font-size: 9px; padding: 1px 5px;">运镜成片</span>' : '<span class="tag" style="font-size: 9px; padding: 1px 5px;">原始录制</span>'}
              </div>
              <div class="mono" style="font-size: 10px; color: var(--text-muted); margin-top: 3px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span>${item.source} · ${item.size} · 时长 ${item.durationText}</span>
                ${item.matchedProject ? `<span style="color: var(--color-accent-text); font-weight: 500;">匹配工程: ${item.matchedProject} (${item.matchConfidence})</span>` : ''}
              </div>
            </div>
            <span class="tag mono ${item.path === activeVideoPath ? 'tag-active' : ''}">${item.path === activeVideoPath ? 'ACTIVE' : 'SELECT'}</span>
          </div>
        `).join('');

        if (!activeVideoPath && items.length > 0) {
          const preferred = items.find(it => it.isExported || it.name.startsWith('export-')) || items[0];
          selectVideo(preferred.path, preferred.duration, preferred.isExported);
        }
      } catch (err) {
        listEl.innerHTML = '<div style="color: var(--color-danger); padding: 8px;">拉取媒体失败</div>';
      }
    }

    async function selectVideo(path, duration, isExp) {
      activeVideoPath = path;
      activeDuration = duration || 42.5;

      const motionTag = document.getElementById('video-motion-tag');
      if (motionTag) {
        if (isExp) {
          motionTag.className = 'tag mono tag-active';
          motionTag.innerText = '带运镜动效';
          motionTag.title = '当前为 OpenScreen 导出的带缩放动效成片';
        } else {
          motionTag.className = 'tag mono';
          motionTag.innerText = '原始录制底稿';
          motionTag.title = '当前为未带缩放的原始录屏底稿';
        }
      }

      document.querySelectorAll('#media-library-list .card').forEach(c => {
        if (c.dataset.path === path) {
          c.style.borderColor = 'var(--color-accent)';
          c.style.background = 'var(--color-accent-subtle)';
          const tag = c.querySelector('.tag:last-child');
          if (tag) { tag.className = 'tag mono tag-active'; tag.innerText = 'ACTIVE'; }
        } else {
          c.style.borderColor = 'var(--border-subtle)';
          c.style.background = 'var(--bg-surface-raised)';
          const tag = c.querySelector('.tag:last-child');
          if (tag) { tag.className = 'tag mono'; tag.innerText = 'SELECT'; }
        }
      });

      const player = document.getElementById('stage-player');
      player.src = '/media?path=' + encodeURIComponent(path);

      player.ontimeupdate = () => {
        const cur = formatTime(player.currentTime);
        const total = formatTime(player.duration || activeDuration);
        document.getElementById('video-timer-badge').innerText = `${cur} / ${total}`;

        const playhead = document.getElementById('timeline-playhead');
        if (playhead && activeDuration > 0) {
          playhead.style.left = Math.min(100, (player.currentTime / activeDuration) * 100) + '%';
        }

        // 实时音画分镜高亮联动
        const curSec = player.currentTime;
        const phases = window.activePhases || [];
        if (phases.length > 0) {
          const curPhase = phases.find(p => curSec >= p.start && curSec < p.end);
          const activeIdx = curPhase ? curPhase.index : (curSec >= phases[phases.length - 1].start ? phases[phases.length - 1].index : 1);

          document.querySelectorAll('.phase-storyboard-block').forEach(el => {
            const pIdx = parseInt(el.dataset.index, 10);
            if (pIdx === activeIdx) {
              el.style.border = '1px solid var(--color-accent)';
              el.style.boxShadow = '0 0 10px rgba(59,130,246,0.6)';
              el.style.transform = 'translateY(-1px)';
            } else {
              el.style.border = '1px solid var(--border-subtle)';
              el.style.boxShadow = 'none';
              el.style.transform = 'none';
            }
          });

          document.querySelectorAll('.storyboard-phase-card').forEach(el => {
            const pIdx = parseInt(el.dataset.index, 10);
            if (pIdx === activeIdx) {
              el.style.outline = '1px solid var(--color-accent)';
              el.style.boxShadow = '0 0 8px rgba(59,130,246,0.3)';
            } else {
              el.style.outline = 'none';
              el.style.boxShadow = 'none';
            }
          });
        }
      };

      await fetchBeats(path);

      document.getElementById('duration-target-pill').innerText = `视频时长: ${activeDuration.toFixed(1)}s (预算约 ${Math.round(activeDuration * 4.3)} 字)`;

      handleScriptInput();
    }

    function formatTime(sec) {
      if (isNaN(sec)) return "00:00.0";
      const m = Math.floor(sec / 60);
      const s = (sec % 60).toFixed(1);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(4, '0')}`;
    }

    async function fetchBeats(videoPath) {
      const container = document.getElementById('beats-timeline-bar');
      const badge = document.getElementById('beats-count-badge');
      const breakdown = document.getElementById('beats-breakdown-text');
      const chips = document.getElementById('beats-chips-container');
      const phasesBar = document.getElementById('phases-storyboard-bar');
      
      container.innerHTML = '<div id="timeline-playhead" style="position: absolute; top:0; bottom:0; width: 2px; background: #ef4444; z-index: 10; pointer-events: none; left: 0%; box-shadow: 0 0 6px #ef4444;"></div>';
      if (chips) chips.innerHTML = '';
      if (phasesBar) phasesBar.innerHTML = '';

      try {
        const res = await fetch('/api/beats?video=' + encodeURIComponent(videoPath));
        const data = await res.json();
        const beats = Array.isArray(data) ? data : (data.beats || []);
        const phases = Array.isArray(data) ? [] : (data.phases || []);

        activeBeats = beats;
        window.activePhases = phases;

        const zooms = beats.filter(b => b.type === 'zoom');
        const clicks = beats.filter(b => b.type === 'click');

        badge.innerText = `${beats.length} 处动作`;
        if (breakdown) {
          const mInfo = data.matchInfo || {};
          let matchNote = '';
          if (mInfo.projectName) {
            matchNote = ` · 已匹配 ${mInfo.projectName} (${mInfo.confidence || '100%'})`;
          }
          breakdown.innerText = `${zooms.length} 处特写 · ${clicks.length} 次交互${matchNote}`;
          if (mInfo.reasons && mInfo.reasons.length > 0) {
            breakdown.title = `匹配依据:
` + mInfo.reasons.join('\n');
          }
        }

        const duration = Math.max(1, activeDuration);

        // 渲染 10s 刻度标尺虚线
        for (let s = 10; s < duration; s += 10) {
          const tickPct = (s / duration) * 100;
          const tick = document.createElement('div');
          tick.style.cssText = `position: absolute; left: ${tickPct}%; top: 0; bottom: 0; width: 1px; background: var(--border-subtle); z-index: 1; pointer-events: none;`;
          const tickLabel = document.createElement('span');
          tickLabel.innerText = `${s}s`;
          tickLabel.className = 'mono';
          tickLabel.style.cssText = `position: absolute; left: ${tickPct}%; top: 2px; font-size: 8px; color: var(--text-muted); transform: translateX(-50%); pointer-events: none; z-index: 2;`;
          container.appendChild(tick);
          container.appendChild(tickLabel);
        }

        // 渲染动作标记 (特写色块 + 点击定位钉)
        beats.forEach((b, idx) => {
          const leftPct = Math.min(100, Math.max(0, (b.start / duration) * 100));

          if (b.type === 'zoom') {
            const endSec = b.end || (b.start + 2.1);
            const widthPct = Math.max(2.5, Math.min(100 - leftPct, ((endSec - b.start) / duration) * 100));
            
            const marker = document.createElement('div');
            marker.className = 'beat-marker beat-zoom';
            marker.style.cssText = `position: absolute; left: ${leftPct}%; width: ${widthPct}%; top: 4px; bottom: 4px; background: var(--color-accent-subtle); border: 1px solid var(--color-accent); border-radius: 3px; cursor: pointer; z-index: 4;`;
            marker.title = `镜头特写: ${b.start}s ~ ${endSec}s (点击跳转)`;
            marker.onclick = (e) => {
              e.stopPropagation();
              seekTo(b.start);
            };
            container.appendChild(marker);
          } else {
            const marker = document.createElement('div');
            marker.className = 'beat-marker beat-click';
            marker.style.cssText = `position: absolute; left: ${leftPct}%; width: 4px; top: 3px; bottom: 3px; background: var(--color-warning); border-radius: 2px; cursor: pointer; z-index: 5; transform: translateX(-50%); box-shadow: 0 0 4px rgba(251,191,36,0.6);`;
            marker.title = `鼠标交互: ${b.start}s (点击跳转)`;
            marker.onclick = (e) => {
              e.stopPropagation();
              seekTo(b.start);
            };
            container.appendChild(marker);
          }
        });

        container.onclick = (e) => {
          const rect = container.getBoundingClientRect();
          const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
          seekTo(ratio * duration);
        };

        // 渲染分镜阶段条
        if (phasesBar && phases.length > 0) {
          phasesBar.innerHTML = phases.map(p => {
            const isZoom = p.type === 'zoom';
            const bg = isZoom ? 'var(--color-accent-subtle)' : 'var(--bg-surface-raised)';
            const border = isZoom ? 'rgba(59,130,246,0.3)' : 'var(--border-subtle)';
            return `
              <div class="phase-storyboard-block mono" data-index="${p.index}"
                   style="flex: ${p.duration}; min-width: 48px; background: ${bg}; border: 1px solid ${border}; border-radius: 4px; padding: 2px 4px; font-size: 9.5px; display: flex; flex-direction: column; justify-content: center; align-items: center; cursor: pointer; transition: transform 120ms ease, box-shadow 120ms ease; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;"
                   onclick="seekToPhase(${p.index}, ${p.start})" title="分镜 P${p.index} [${p.start}s~${p.end}s] ${p.label}
${p.hint}
预算 ${p.char_budget} 字 (点击跳转)">
                <span style="font-weight: 600; color: ${isZoom ? 'var(--color-accent-text)' : 'var(--text-primary)'}; pointer-events: none;">P${p.index} ${p.start}s</span>
                <span style="font-size: 8.5px; color: var(--text-muted); pointer-events: none;">${p.label.split(' ')[0]}</span>
              </div>
            `;
          }).join('');
        }

        // 渲染底部微缩动作标签栏
        if (chips) {
          if (beats.length > 0) {
            chips.innerHTML = beats.map((b, i) => `
              <button class="btn btn-sm mono" style="padding: 2px 7px; font-size: 10px; border-radius: 12px; white-space: nowrap; background: var(--bg-surface-raised); border-color: var(--border-subtle);"
                      onclick="seekTo(${b.start})" title="${b.type === 'zoom' ? `特写镜头 (${b.start}s~${b.end||''}s)` : `鼠标点击 (${b.start}s)`}">
                ${b.start}s ${b.type === 'zoom' ? '特写' : '点击'}
              </button>
            `).join('');
          } else {
            chips.innerHTML = '<span class="mono" style="font-size: 10px; color: var(--text-muted);">未检测到遥测动作点</span>';
          }
        }

        updateStoryboardMonitor();

      } catch (err) {
        console.error('Fetch beats error:', err);
        badge.innerText = `0 处动作`;
        if (breakdown) breakdown.innerText = `遥测读取异常`;
      }
    }

    function seekTo(sec) {
      const player = document.getElementById('stage-player');
      if (player) {
        player.currentTime = Math.max(0, Math.min(player.duration || activeDuration, sec));
        player.play();
      }
    }

    function seekToPhase(idx, startSec) {
      seekTo(startSec);
      const textarea = document.getElementById('script-textarea');
      if (!textarea) return;
      const paragraphs = textarea.value.split(/\n\s*\n/);
      if (paragraphs.length >= idx) {
        let startPos = 0;
        for (let i = 0; i < idx - 1; i++) {
          startPos += paragraphs[i].length + 2;
        }
        const endPos = startPos + paragraphs[idx - 1].length;
        textarea.focus();
        textarea.setSelectionRange(startPos, endPos);
      }
    }

    function updateStoryboardMonitor() {
      const monitor = document.getElementById('storyboard-sync-monitor');
      const container = document.getElementById('storyboard-phase-cards');
      const summaryTag = document.getElementById('storyboard-sync-summary');
      if (!monitor || !container) return;

      const phases = window.activePhases || [];
      if (!phases || phases.length === 0) {
        monitor.style.display = 'none';
        return;
      }

      monitor.style.display = 'block';

      const text = document.getElementById('script-textarea').value.trim();
      const paras = text.split(/\n\s*\n/).map(p => p.trim()).filter(p => p.length > 0);

      let fitCount = 0;
      let overCount = 0;

      container.innerHTML = phases.map((p, idx) => {
        const paraText = paras[idx] || "";
        const cCount = paraText.replace(/\s+/g, '').length;
        const budget = p.char_budget || 20;

        let statusClass = "tag";
        let statusText = "待生成";
        let borderColor = "var(--border-subtle)";
        let bg = "var(--bg-surface-raised)";

        if (cCount > 0) {
          if (Math.abs(cCount - budget) <= 5) {
            statusClass = "tag tag-active";
            statusText = `${cCount}/${budget}字`;
            borderColor = "var(--color-success)";
            bg = "var(--color-success-subtle)";
            fitCount++;
          } else if (cCount > budget + 5) {
            statusClass = "tag";
            statusText = `偏长 ${cCount}/${budget}字`;
            borderColor = "var(--color-danger)";
            bg = "var(--color-danger-subtle)";
            overCount++;
          } else {
            statusClass = "tag";
            statusText = `稍短 ${cCount}/${budget}字`;
            borderColor = "var(--color-warning)";
            bg = "var(--color-warning-subtle)";
            fitCount++;
          }
        }

        return `
          <div class="storyboard-phase-card card mono" data-index="${p.index}"
               style="padding: 6px 8px; border: 1px solid ${borderColor}; background: ${bg}; cursor: pointer; border-radius: 6px; transition: transform 120ms ease;"
               onclick="seekToPhase(${p.index}, ${p.start})"
               title="分镜 P${p.index} [${p.start}s~${p.end}s]
${p.hint}
台词: ${paraText || '(尚未生成)'}
点击视频跳转至该分镜">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
              <span style="font-weight: 700; font-size: 10px; color: var(--text-primary); border-bottom: 1px dashed var(--border-default);"
                    title="点击微调该分镜开口秒数（合成时将严格硬锚定至该时间点）"
                    onclick="event.stopPropagation(); editPhaseStartTime(${idx})">P${p.index} · ${p.start}s ✎</span>
              <span class="${statusClass}" style="font-size: 9px; padding: 1px 4px;">${statusText}</span>
            </div>
            <div style="font-size: 9.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              ${p.label}
            </div>
          </div>
        `;
      }).join('');

      if (summaryTag) {
        if (paras.length === 0) {
          summaryTag.innerText = `已解析 ${phases.length} 处分镜 · 等待拟合`;
          summaryTag.className = "tag mono";
        } else if (overCount === 0 && fitCount >= phases.length) {
          summaryTag.innerText = `${phases.length} 处分镜全对齐 (时间轴硬锚定)`;
          summaryTag.className = "tag mono tag-active";
        } else if (overCount > 0) {
          summaryTag.innerText = `${overCount} 段偏长 (合成将自动微加速卡点)`;
          summaryTag.className = "tag mono";
          summaryTag.style.color = "var(--color-warning)";
        } else {
          summaryTag.innerText = `已锚定 ${fitCount}/${phases.length} 分镜`;
          summaryTag.className = "tag mono tag-active";
        }
      }
    }

    function editPhaseStartTime(idx) {
      const phases = window.activePhases || [];
      if (!phases[idx]) return;
      const curStart = phases[idx].start;
      const minStart = idx === 0 ? 0.0 : +(phases[idx - 1].start + 0.5).toFixed(1);
      const maxStart = +(phases[idx].end - 0.5).toFixed(1);
      const input = prompt(`微调分镜 P${phases[idx].index} 的开口起始秒数 (范围 ${minStart}s ~ ${maxStart}s)：\n合成时配音将严格锚定在此秒数准时开口。`, curStart);
      if (input === null) return;
      const val = parseFloat(input);
      if (isNaN(val) || val < minStart || val > maxStart) {
        alert(`请输入 ${minStart} 到 ${maxStart} 之间的有效秒数`);
        return;
      }
      const newStart = +val.toFixed(1);
      phases[idx].start = newStart;
      phases[idx].duration = +(phases[idx].end - newStart).toFixed(1);
      phases[idx].char_budget = Math.max(10, Math.round(phases[idx].duration * 4.2));
      if (idx > 0) {
        phases[idx - 1].end = newStart;
        phases[idx - 1].duration = +(newStart - phases[idx - 1].start).toFixed(1);
        phases[idx - 1].char_budget = Math.max(10, Math.round(phases[idx - 1].duration * 4.2));
      }
      updateStoryboardMonitor();
      seekToPhase(phases[idx].index, newStart);
    }

    function updateSpeedMeter(val) {
      const v = parseInt(val, 10);
      document.getElementById('rate-label').innerText = (v >= 0 ? `+${v}%` : `${v}%`);
      const base = 4.3 * (1 + v / 100);
      document.getElementById('speed-meter').innerText = `${base.toFixed(1)} 字/秒`;
      recalculateMetrics();
    }

    function recalculateMetrics() {
      const text = document.getElementById('script-textarea').value.trim();
      const chars = text.replace(/\s+/g, '').length;
      
      const v = parseInt(document.getElementById('rate-slider').value, 10);
      const charsPerSec = 4.3 * (1 + v / 100);
      const estSec = chars > 0 ? (chars / charsPerSec) : 0;
      const delta = estSec - activeDuration;

      document.getElementById('char-count-text').innerText = `字数: ${chars} 字`;
      document.getElementById('speech-sec-text').innerText = `朗读预估: ${estSec.toFixed(1)}s`;

      const deltaEl = document.getElementById('delta-sec-text');
      const statusBadge = document.getElementById('fit-status-badge');

      if (chars === 0) {
        deltaEl.innerText = "时间偏差: 0.0s";
        statusBadge.className = "tag";
        statusBadge.innerText = "无文本";
        statusBadge.style.color = "var(--text-muted)";
        return;
      }

      if (Math.abs(delta) <= 4.0) {
        deltaEl.innerText = `时间偏差: ${delta > 0 ? '+' : ''}${delta.toFixed(1)}s (契合)`;
        deltaEl.style.color = "var(--color-success)";
        statusBadge.className = "tag tag-active";
        statusBadge.innerText = "严丝合缝";
        statusBadge.style.background = "var(--color-success-subtle)";
        statusBadge.style.color = "var(--color-success)";
      } else if (delta > 4.0) {
        deltaEl.innerHTML = `时间偏差: +${delta.toFixed(1)}s (偏长) <button class="btn btn-sm" type="button" onclick="triggerSmartTrim()" style="padding: 1px 8px; font-size: 10px; margin-left: 6px; background: var(--color-danger); color: #fff; border: none; border-radius: 4px; cursor: pointer;">一键裁剪</button>`;
        deltaEl.style.color = "var(--color-danger)";
        statusBadge.className = "tag";
        statusBadge.innerHTML = `超时 ${Math.round(delta)}s`;
        statusBadge.style.background = "var(--color-danger-subtle)";
        statusBadge.style.color = "var(--color-danger)";
      } else {
        deltaEl.innerText = `时间偏差: ${delta.toFixed(1)}s (空余)`;
        deltaEl.style.color = "var(--color-warning)";
        statusBadge.className = "tag";
        statusBadge.innerText = `空余 ${Math.round(-delta)}s`;
        statusBadge.style.background = "var(--color-warning-subtle)";
        statusBadge.style.color = "var(--color-warning)";
      }
      updateStoryboardMonitor();
    }

    function handleScriptInput() {
      const text = document.getElementById('script-textarea').value.trim();
      const btn = document.getElementById('btn-adapt-script');
      const hint = document.getElementById('adapt-hint-badge');
      
      if (text.length >= 4) {
        if (btn) {
          btn.disabled = false;
          btn.style.opacity = '1';
          btn.style.cursor = 'pointer';
        }
        if (hint) {
          hint.innerText = '准备就绪，点击执行分镜拟合';
          hint.style.color = 'var(--color-accent-text)';
        }
      } else {
        if (btn) {
          btn.disabled = true;
          btn.style.opacity = '0.45';
          btn.style.cursor = 'not-allowed';
        }
        if (hint) {
          hint.innerText = '下方输入操作要点后激活';
          hint.style.color = 'var(--text-muted)';
        }
      }
      recalculateMetrics();
    }

    function openLlmModal() {
      document.getElementById('llm-modal').style.display = 'flex';
      loadLlmConfig();
    }

    function closeLlmModal() {
      document.getElementById('llm-modal').style.display = 'none';
    }

    function handleProviderChange(val) {
      const preset = PROVIDER_PRESETS[val];
      if (preset) {
        document.getElementById('llm-url-input').value = preset.url;
        document.getElementById('llm-model-input').value = preset.model;
      }
    }

    function toggleKeyVisibility() {
      const el = document.getElementById('llm-key-input');
      el.type = el.type === 'password' ? 'text' : 'password';
    }

    function appendStyleTag(text) {
      const ta = document.getElementById('llm-style-prompt');
      if (!ta.value.includes(text)) {
        ta.value = ta.value.trim() ? `${ta.value.trim()}\n• ${text}` : `• ${text}`;
      }
    }

    async function loadLlmConfig() {
      try {
        const res = await fetch('/api/llm-config');
        const cfg = await res.json();
        window.currentLlmConfig = cfg;

        const pSel = document.getElementById('llm-provider-select');
        if (pSel && cfg.provider) pSel.value = cfg.provider;

        const uIn = document.getElementById('llm-url-input');
        if (uIn && cfg.apiUrl) uIn.value = cfg.apiUrl;

        const mIn = document.getElementById('llm-model-input');
        if (mIn && cfg.model) mIn.value = cfg.model;

        const kIn = document.getElementById('llm-key-input');
        if (kIn && cfg.apiKey) kIn.value = cfg.apiKey;

        const sPrompt = document.getElementById('llm-sys-prompt');
        if (sPrompt && cfg.systemPrompt) sPrompt.value = cfg.systemPrompt;

        const stPrompt = document.getElementById('llm-style-prompt');
        if (stPrompt && cfg.stylePrompt) stPrompt.value = cfg.stylePrompt;

        updateLlmStatusBadge(cfg);
      } catch (err) {
        console.error('加载大模型配置失败:', err);
      }
    }

    function updateLlmStatusBadge(cfg) {
      const pill = document.getElementById('llm-status-pill');
      if (!pill) return;
      if (cfg && cfg.apiKey && cfg.apiKey.trim()) {
        pill.className = 'tag mono tag-active';
        const name = cfg.provider === 'deepseek' ? 'DeepSeek' : cfg.provider === 'openai' ? 'OpenAI' : (cfg.model || '大模型');
        pill.innerText = `${name} 就绪`;
      } else {
        pill.className = 'tag mono';
        pill.innerText = '未配置 Key';
      }
    }

    async function testLlmConn() {
      const btn = document.getElementById('btn-test-llm');
      const msg = document.getElementById('test-conn-msg');
      btn.disabled = true;
      btn.innerText = '测试中...';
      msg.innerText = '';

      const payload = {
        provider: document.getElementById('llm-provider-select').value,
        apiUrl: document.getElementById('llm-url-input').value.trim(),
        model: document.getElementById('llm-model-input').value.trim(),
        apiKey: document.getElementById('llm-key-input').value.trim()
      };

      try {
        const res = await fetch('/api/test-llm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          msg.style.color = 'var(--color-success)';
          msg.innerText = data.message;
        } else {
          msg.style.color = 'var(--color-danger)';
          msg.innerText = data.message;
        }
      } catch (err) {
        msg.style.color = 'var(--color-danger)';
        msg.innerText = '连接测试失败: ' + err.message;
      } finally {
        btn.disabled = false;
        btn.innerText = '测试连通性';
      }
    }

    async function saveLlmSettings() {
      const payload = {
        provider: document.getElementById('llm-provider-select').value,
        apiUrl: document.getElementById('llm-url-input').value.trim(),
        model: document.getElementById('llm-model-input').value.trim(),
        apiKey: document.getElementById('llm-key-input').value.trim(),
        systemPrompt: document.getElementById('llm-sys-prompt').value.trim(),
        stylePrompt: document.getElementById('llm-style-prompt').value.trim()
      };

      try {
        const res = await fetch('/api/llm-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          window.currentLlmConfig = payload;
          updateLlmStatusBadge(payload);
          closeLlmModal();
          alert('大模型配置与提示词已保存。现在点击拟合按钮即可体验分镜深度润色。');
        } else {
          alert('保存失败');
        }
      } catch (err) {
        alert('保存异常: ' + err.message);
      }
    }

    async function triggerSmartAdaptScript() {
      const text = document.getElementById('script-textarea').value.trim();
      if (text.length < 4) {
        alert('请先在下方输入框中写下您的操作步骤或要点！');
        return;
      }
      const btn = document.getElementById('btn-adapt-script');
      const hint = document.getElementById('adapt-hint-badge');
      btn.innerText = '正在精准拟合分镜...';
      btn.disabled = true;
      if (hint) {
        hint.innerText = '正在按视频秒数与分镜节拍计算最优表达...';
        hint.style.color = 'var(--color-warning)';
      }

      try {
        const res = await fetch('/api/ai-adapt-script', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            duration: activeDuration,
            videoPath: activeVideoPath
          })
        });
        const data = await res.json();
        if (data.script) {
          document.getElementById('script-textarea').value = data.script;
          if (data.phases && data.phases.length > 0) {
            window.activePhases = data.phases;
          }
          handleScriptInput();
          updateStoryboardMonitor();
          if (hint) {
            hint.innerText = data.message || '分镜文案拟合完成';
            hint.style.color = data.source === 'llm' ? 'var(--color-accent-text)' : 'var(--color-success)';
          }
        } else {
          alert('拟合未能生成文案: ' + (data.message || '未知原因'));
        }
      } catch (err) {
        alert('拟合失败: ' + err.message);
      } finally {
        btn.innerText = '智能拟合分镜文案';
        btn.disabled = false;
      }
    }

    async function triggerSmartTrim() {
      const text = document.getElementById('script-textarea').value.trim();
      if (!text) return;
      try {
        const res = await fetch('/api/ai-trim', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            duration: activeDuration
          })
        });
        const data = await res.json();
        if (data.script) {
          document.getElementById('script-textarea').value = data.script;
          handleScriptInput();
        }
      } catch (err) {
        console.error('一键裁剪失败:', err);
      }
    }

    async function startMasterSynthesis() {
      const script = document.getElementById('script-textarea').value.trim();
      if (!script) {
        alert('请先编写或生成解说词台词！');
        return;
      }
      if (!activeVideoPath) {
        alert('请先选择一段录屏视频！');
        return;
      }

      const bilingualSubs = document.getElementById('bilingual-sub-toggle') ? document.getElementById('bilingual-sub-toggle').checked : false;
      const langSelVal = document.getElementById('bilingual-lang-select') ? document.getElementById('bilingual-lang-select').value : 'English';
      const customLangVal = document.getElementById('bilingual-custom-lang') ? document.getElementById('bilingual-custom-lang').value.trim() : '';
      const targetLang = (langSelVal === 'custom') ? (customLangVal || 'English') : langSelVal;
      const bilingualOrder = document.getElementById('bilingual-order-select') ? document.getElementById('bilingual-order-select').value : 'orig_top';

      if (bilingualSubs) {
        const hasLlmKey = window.currentLlmConfig && window.currentLlmConfig.apiKey && window.currentLlmConfig.apiKey.trim();
        if (!hasLlmKey) {
          alert('开启「双语字幕」需要借助大模型翻译能力。请先配置并保存您的 AI 大模型 API Key！');
          openLlmModal();
          return;
        }
        if (langSelVal === 'custom' && !customLangVal) {
          alert('请先填写自定义目标语言名称（如：泰语、阿拉伯语），或选择内置语种！');
          return;
        }
      }

      const btn = document.getElementById('render-master-btn');
      btn.disabled = true;
      if (activeVoice === 'my_voice' || (voicesList.find(x => x.id === activeVoice) || {}).type === 'custom') {
        btn.innerText = bilingualSubs
          ? '🧠 专属音色推理 + 大模型双语翻译与压制中，请耐心稍候...'
          : '🧠 专属音色本地神经推理与对齐中 (约需40~60秒)，请耐心稍候...';
      } else {
        btn.innerText = bilingualSubs
          ? `正在进行 AI 配音、大模型翻译 (${targetLang}) 与双语压制，请稍候...`
          : '正在进行音视频精确对齐与字幕压制，请稍候...';
      }

      const v = parseInt(document.getElementById('rate-slider').value, 10);
      const rateStr = v >= 0 ? `+${v}%` : `${v}%`;
      const burnSubs = document.getElementById('burn-sub-toggle').checked;
      const holdLastFrame = document.getElementById('hold-last-frame-toggle') ? document.getElementById('hold-last-frame-toggle').checked : true;
      const fontSize = document.getElementById('sub-fontsize-select').value || "10.5";

      try {
        const res = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            videoPath: activeVideoPath,
            script: script,
            voice: activeVoice,
            rate: rateStr,
            burnSubtitles: burnSubs,
            fontSize: fontSize,
            holdLastFrame: holdLastFrame,
            bilingualSubtitles: bilingualSubs,
            targetLanguage: targetLang,
            bilingualOrder: bilingualOrder,
            phases: window.activePhases || [],
            phaseLock: true,
            privacyBlurs: privacyBlurs || []
          })
        });

        const data = await res.json();
        if (!data.success) throw new Error(data.error);

        const deck = document.getElementById('result-deck');
        const player = document.getElementById('final-playback-monitor');
        const badge = document.getElementById('result-filename-badge');
        const biBadge = document.getElementById('result-bilingual-badge');

        deck.style.display = 'block';
        player.src = data.videoUrl;
        badge.innerText = data.videoName;

        if (biBadge) {
          if (data.bilingualWarning) {
            biBadge.style.display = 'inline-flex';
            biBadge.className = 'tag mono';
            biBadge.style.background = 'var(--color-warning-subtle)';
            biBadge.style.color = 'var(--color-warning)';
            biBadge.style.borderColor = 'var(--color-warning)';
            biBadge.innerText = '⚠ ' + data.bilingualWarning;
          } else if (data.bilingualApplied) {
            biBadge.style.display = 'inline-flex';
            biBadge.className = 'tag mono tag-active';
            biBadge.style.background = '';
            biBadge.style.color = '';
            biBadge.style.borderColor = '';
            biBadge.innerText = `双语字幕 (${targetLang})`;
          } else {
            biBadge.style.display = 'none';
          }
        }

        document.getElementById('btn-dl-video').href = data.videoUrl;
        document.getElementById('btn-dl-video').download = data.videoName;
        document.getElementById('btn-dl-mp3').href = data.audioUrl;
        document.getElementById('btn-dl-srt').href = data.srtUrl;

        renderSyncCheckReport(data.phaseMetrics || [], data.gridUrl || '');
        fetchHistoryProjects();

        deck.scrollIntoView({ behavior: 'smooth' });
        player.play();
      } catch (err) {
        alert('渲染失败: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerText = '导出成片 (渲染视频 + AI配音 + 同步字幕)';
      }
    }

    initWorkbench();
  
  </script>
</body>
</html>"""

def get_edge_tts_cmd():
    """获取 edge-tts 执行命令 (支持本地虚拟环境/系统 PATH、uvx 或 python 模块调用)"""
    if shutil.which("edge-tts"):
        return ["edge-tts"]
    if shutil.which("uvx"):
        return ["uvx", "edge-tts"]
    return [sys.executable, "-m", "edge_tts"]

def get_video_duration(file_path):
    try:
        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)]
        res = subprocess.run(dur_cmd, capture_output=True, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def sanitize_srt(raw_text: str) -> str:
    """保证 SRT 格式纯净：精确递增编号、严谨时间戳、彻底剔除多余数字或空行"""
    import re
    blocks = re.split(r'\n\s*\n', raw_text.strip())
    clean_blocks = []
    idx = 1
    for b in blocks:
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        time_line_idx = -1
        for i, l in enumerate(lines):
            if '-->' in l:
                time_line_idx = i
                break
        if time_line_idx == -1:
            continue
        
        time_line = lines[time_line_idx].replace('.', ',')
        text_lines = []
        for l in lines[time_line_idx + 1:]:
            # 彻底杜绝纯数字序号作为文本输出到画面
            if l.isdigit():
                continue
            text_lines.append(l)
        
        if text_lines:
            clean_blocks.append(f"{idx}\n{time_line}\n" + "\n".join(text_lines))
            idx += 1
            
    return "\n\n".join(clean_blocks) + "\n"

class WorkbenchHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_WORKBENCH.encode("utf-8"))
            return

        elif path == "/api/voices":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(get_all_voices(), ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/api/llm-config":
            cfg = load_llm_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cfg, ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/api/preview-voice":
            all_v = get_all_voices()
            raw_vid = query.get("voice", [all_v[0]["id"]])[0]
            voice_entry = next((v for v in all_v if v["id"] == raw_vid), all_v[0])
            safe_vid = re.sub(r"[^a-zA-Z0-9_-]", "", str(voice_entry["id"])) or "default"
            preview_file = OUTPUT_DIR / f"preview_{safe_vid}.mp3"

            if not preview_file.exists():
                try:
                    if voice_entry.get("type") == "custom":
                        ok, err_msg = check_custom_tts_available()
                        if not ok:
                            self.send_response(500)
                            self.send_header("Content-Type", "application/json; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": err_msg}).encode("utf-8"))
                            return
                        custom_runner = BASE_DIR / "custom_voice_tts.py"
                        ref_audio = CUSTOM_VOICE_DIR / voice_entry.get("ref_audio", "my_recording.wav")
                        ref_text = voice_entry.get("ref_text", "")
                        py_bin = get_custom_tts_python()
                        cmd = [
                            py_bin, str(custom_runner),
                            "--text", f"你好，我是{voice_entry['name']}，很高兴为您带来本期教程解说。",
                            "--output-audio", str(preview_file),
                            "--output-srt", str(preview_file.with_suffix(".srt")),
                            "--ref-audio", str(ref_audio),
                            "--ref-text", ref_text
                        ]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
                    else:
                        text = f"你好，我是{voice_entry['name']}，很高兴为您带来本期功能教程解说。"
                        cmd = get_edge_tts_cmd() + ["--voice", voice_entry["voice_id"], "--text", text, "--write-media", str(preview_file)]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
                except subprocess.TimeoutExpired:
                    preview_file.unlink(missing_ok=True)
                    self.send_response(504)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "试听音频合成超时，请检查网络连接"}).encode("utf-8"))
                    return
                except Exception as e:
                    preview_file.unlink(missing_ok=True)
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"试听合成异常: {str(e)}"}).encode("utf-8"))
                    return

            if not preview_file.exists():
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "生成试听音频失败，请检查网络连接或运行依赖"}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"url": f"/media?path={urllib.parse.quote(str(preview_file))}"}).encode("utf-8"))
            return

        elif path == "/api/beats":
            video_path = query.get("video", [""])[0]
            override_proj = query.get("project", [""])[0]
            beats = []
            phases = []
            match_info = {}
            total_dur = 0.0
            if video_path and os.path.exists(video_path):
                v_path = Path(video_path)
                beats = extract_openscreen_beats(v_path, override_proj)
                total_dur = get_video_duration(v_path)
                phases = analyze_telemetry_phases(beats, total_dur, video_path=v_path)
                _, _, match_info = find_matching_openscreen_project(v_path, override_proj)

            avail_projs = list_available_openscreen_projects()

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "beats": beats,
                "phases": phases,
                "matchedProject": match_info.get("projectName", ""),
                "matchInfo": match_info,
                "availableProjects": avail_projs,
                "duration": total_dur
            }, ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/api/projects":
            projects = []
            if OUTPUT_DIR.exists():
                for pf in sorted(OUTPUT_DIR.glob("project_*.json"), key=os.path.getmtime, reverse=True)[:30]:
                    try:
                        p_data = json.loads(pf.read_text(encoding="utf-8"))
                        p_data["id"] = pf.stem
                        projects.append(p_data)
                    except Exception:
                        continue
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"projects": projects}, ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/api/recordings":
            recordings = []
            seen_paths = set()

            # 1. 扫描 Downloads 目录中 OpenScreen 导出的带运镜动效成片 (export-*.mp4)
            if DOWNLOADS_DIR.exists():
                for f in sorted(DOWNLOADS_DIR.glob("export-*.mp4"), key=os.path.getmtime, reverse=True):
                    resolved = str(f.resolve())
                    if resolved in seen_paths: continue
                    dur = get_video_duration(f)
                    mins, secs = int(dur // 60), int(dur % 60)
                    dur_text = f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"
                    size_mb = round(f.stat().st_size / (1024 * 1024), 1)
                    _, _, m_info = find_matching_openscreen_project(f)
                    recordings.append({
                        "name": f.name,
                        "path": resolved,
                        "size": f"{size_mb} MB",
                        "source": "OpenScreen 导出成片",
                        "isExported": True,
                        "duration": dur,
                        "durationText": dur_text,
                        "matchedProject": m_info.get("projectName", ""),
                        "matchConfidence": m_info.get("confidence", "")
                    })
                    seen_paths.add(resolved)

            # 2. 用户上传/导入的
            if UPLOADS_DIR.exists():
                for f in sorted(UPLOADS_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
                    if f.suffix.lower() in [".mp4", ".mov", ".webm", ".mkv"]:
                        resolved = str(f.resolve())
                        if resolved in seen_paths: continue
                        dur = get_video_duration(f)
                        mins, secs = int(dur // 60), int(dur % 60)
                        dur_text = f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"
                        size_mb = round(f.stat().st_size / (1024 * 1024), 1)
                        is_exp = f.name.startswith("export-")
                        recordings.append({
                            "name": f.name,
                            "path": resolved,
                            "size": f"{size_mb} MB",
                            "source": "OpenScreen 导出成片" if is_exp else "外部导入视频",
                            "isExported": is_exp,
                            "duration": dur,
                            "durationText": dur_text
                        })
                        seen_paths.add(resolved)

            # 3. OpenScreen 默认录屏目录 (原始录制底稿，无运镜)
            if RECORDINGS_DIR.exists():
                for f in sorted(RECORDINGS_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True):
                    resolved = str(f.resolve())
                    if resolved in seen_paths: continue
                    dur = get_video_duration(f)
                    mins, secs = int(dur // 60), int(dur % 60)
                    dur_text = f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"
                    size_mb = round(f.stat().st_size / (1024 * 1024), 1)
                    recordings.append({
                        "name": f.name,
                        "path": resolved,
                        "size": f"{size_mb} MB",
                        "source": "OpenScreen 原始底稿 (无运镜)",
                        "isExported": False,
                        "duration": dur,
                        "durationText": dur_text
                    })
                    seen_paths.add(resolved)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(recordings, ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/media":
            media_path = query.get("path", [""])[0]
            if not media_path or not os.path.exists(media_path):
                self.send_error(404, "File Not Found")
                return

            # 安全校验：严防路径穿越读取任意敏感文件（仅允许授权媒体目录与媒体后缀）
            try:
                req_path = Path(media_path).resolve()
                allowed_roots = [
                    DOWNLOADS_DIR.resolve(),
                    UPLOADS_DIR.resolve(),
                    RECORDINGS_DIR.resolve(),
                    OUTPUT_DIR.resolve()
                ]
                allowed_exts = {".mp4", ".mov", ".webm", ".mkv", ".mp3", ".wav", ".srt"}
                is_in_allowed_dir = any(
                    req_path == r or str(req_path).startswith(str(r) + os.sep)
                    for r in allowed_roots
                )
                if req_path.suffix.lower() not in allowed_exts or not is_in_allowed_dir or not req_path.is_file():
                    self.send_error(403, "Forbidden Media Path")
                    return
                media_path = str(req_path)
            except Exception:
                self.send_error(403, "Invalid Media Path")
                return

            file_size = os.path.getsize(media_path)
            mime = "video/mp4" if media_path.endswith(".mp4") else "audio/mpeg" if media_path.endswith(".mp3") else "text/plain; charset=utf-8"

            # 检查 Range 请求 (HTTP 206 Partial Content 支持，视频流拖拽与断点续传)
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    ranges = range_header[6:].split("-")
                    start = int(ranges[0]) if ranges[0] else 0
                    end = int(ranges[1]) if len(ranges) > 1 and ranges[1] else file_size - 1
                    end = min(end, file_size - 1)
                    if start < 0 or start > end:
                        start = 0
                    content_length = (end - start) + 1

                    self.send_response(206)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(content_length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    if self.command != "HEAD":
                        with open(media_path, "rb") as f:
                            f.seek(start)
                            remaining = content_length
                            while remaining > 0:
                                chunk = f.read(min(remaining, 64 * 1024))
                                if not chunk: break
                                try:
                                    self.wfile.write(chunk)
                                except (BrokenPipeError, ConnectionResetError):
                                    break
                                remaining -= len(chunk)
                    return
                except Exception:
                    pass

            # 正常完整响应
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            if self.command != "HEAD":
                with open(media_path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            break
            return

        super().do_GET()

    def do_HEAD(self):
        self.do_GET()

    def _read_json_body(self) -> dict:
        try:
            length = max(0, int(self.headers.get("Content-Length", 0)))
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/upload":
                raw_filename = query.get("filename", ["video.mp4"])[0]
                clean_name = os.path.basename(urllib.parse.unquote(raw_filename)) or "video.mp4"
                target_path = UPLOADS_DIR / clean_name

                length = max(0, int(self.headers.get("Content-Length", 0)))
                remaining = length
                with open(target_path, "wb") as f:
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 64 * 1024))
                        if not chunk: break
                        f.write(chunk)
                        remaining -= len(chunk)

                dur = get_video_duration(target_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "path": str(target_path.resolve()),
                    "filename": clean_name,
                    "duration": dur
                }).encode("utf-8"))
                return

            elif path == "/api/llm-config":
                data = self._read_json_body()
                save_llm_config(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                return

            elif path == "/api/test-llm":
                data = self._read_json_body()
                ok, msg = test_llm_connection(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": ok, "message": msg}, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/ai-adapt-script":
                data = self._read_json_body()
                text = str(data.get("text") or "")
                duration = safe_duration(data.get("duration"), 42.5)
                raw_vpath = str(data.get("videoPath") or "").strip()
                video_path = Path(raw_vpath) if raw_vpath else None

                res = adapt_script_to_duration(text, duration, video_path)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "script": res.get("script", ""),
                    "source": res.get("source", "rule"),
                    "phases": res.get("phases", []),
                    "paragraphs": res.get("paragraphs", []),
                    "message": res.get("message", "")
                }, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/ai-script":
                data = self._read_json_body()
                raw_vpath = str(data.get("videoPath") or "").strip()
                video_path = Path(raw_vpath) if raw_vpath else None
                duration = safe_duration(data.get("duration"), 42.5)
                topic = str(data.get("topic") or "新建工单与服务派发流程")

                script = generate_script(video_path, duration, topic)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "script": script}, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/ai-compress":
                data = self._read_json_body()
                text = str(data.get("text") or "")
                duration = safe_duration(data.get("duration"), 42.5)

                compressed = compress_script_to_duration(text, duration)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "compressed": compressed}, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/ai-trim":
                data = self._read_json_body()
                text = str(data.get("text") or "")
                duration = safe_duration(data.get("duration"), 42.5)
                target_chars = int(duration * CHARS_PER_SECOND)
                trimmed = compress_text_to_target(text, target_chars)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "script": trimmed}, ensure_ascii=False).encode("utf-8"))
                return

            elif path == "/api/generate":
                data = self._read_json_body()
                raw_vpath = str(data.get("videoPath") or "").strip()
                if not raw_vpath or not os.path.exists(raw_vpath):
                    raise ValueError("未找到指定的源录屏视频文件，请重新选择视频")
                video_path = Path(raw_vpath)
                script = str(data.get("script") or "").strip()
                if not script:
                    raise ValueError("解说词台词不能为空")
                voice_id = str(data.get("voice") or "xiaoxiao")
                rate = str(data.get("rate") or "+0%")
                burn_subs = bool(data.get("burnSubtitles", True))
                hold_last_frame = bool(data.get("holdLastFrame", True))
                bilingual_subs = bool(data.get("bilingualSubtitles", False))
                target_lang = str(data.get("targetLanguage") or "English").strip() or "English"
                bilingual_order = str(data.get("bilingualOrder") or "orig_top").strip()

                all_v = get_all_voices()
                voice_entry = next((v for v in all_v if v["id"] == voice_id), all_v[0])

                ts = f"{int(time.time() * 1000)}_{os.getpid()}"
                prefix = OUTPUT_DIR / f"tutorial_{ts}"
                audio_path = prefix.with_suffix(".mp3")
                srt_path = prefix.with_suffix(".srt")
                ass_path = prefix.with_suffix(".ass")
                final_video = prefix.with_name(f"tutorial_{ts}_final.mp4")

                font_size = safe_duration(data.get("fontSize"), 10.5)
                margin_v = 22 if font_size <= 11.5 else 26

                if not shutil.which("ffmpeg"):
                    raise RuntimeError(
                        "系统未检测到 FFmpeg 核心工具！音视频合成与字幕压制需要 FFmpeg。\n"
                        "👉 Windows: 打开终端运行 `winget install Gyan.FFmpeg`\n"
                        "👉 macOS: 终端运行 `brew install ffmpeg`\n"
                        "安装完成后重新点击导出成片即可！"
                    )

                if voice_entry.get("type") == "custom":
                    ok, err_msg = check_custom_tts_available()
                    if not ok:
                        raise RuntimeError(err_msg)

                    # 专属克隆音色：调用 custom_voice_tts.py
                    speed_factor = 1.0
                    try:
                        speed_pct = int(rate.replace("%", "").replace("+", ""))
                        speed_factor = max(0.5, min(2.0, 1.0 + (speed_pct / 100.0)))
                    except Exception:
                        pass
                    custom_runner = BASE_DIR / "custom_voice_tts.py"
                    ref_audio = CUSTOM_VOICE_DIR / voice_entry.get("ref_audio", "my_recording.wav")
                    ref_text = voice_entry.get("ref_text", "")
                    py_bin = get_custom_tts_python()
                    cmd = [
                        py_bin, str(custom_runner),
                        "--text", script,
                        "--output-audio", str(audio_path),
                        "--output-srt", str(srt_path),
                        "--speed", str(speed_factor),
                        "--ref-audio", str(ref_audio),
                        "--ref-text", ref_text
                    ]
                    custom_tts_timeout = max(900, min(3600, 300 + int(len(script) * 0.8)))
                    try:
                        run_res = subprocess.run(cmd, capture_output=True, text=True, timeout=custom_tts_timeout)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError(f"专属音色神经推理超时（超过 {custom_tts_timeout} 秒），请检查运行日志或切换内置标准音色")
                    if run_res.returncode != 0:
                        err_msg = run_res.stderr.strip()
                        if "f5_tts" in err_msg or "torch" in err_msg or "No module named" in err_msg:
                            raise RuntimeError(
                                "检测到当前环境尚未安装专属声音克隆扩展 (PyTorch / F5-TTS)！\n"
                                "💡 建议直接在左侧选用【晓晓】、【云希】等 7 款内置标准音色（开箱即用，0 门槛秒出片）；\n"
                                "或执行 `pip install f5-tts soundfile` 安装克隆扩展。"
                            )
                        else:
                            raise RuntimeError(f"专属音色合成失败: {err_msg[-400:]}")
                else:
                    # 1. 跑 Edge-TTS 生成音频与干净字幕
                    tts_cmd = get_edge_tts_cmd() + [
                        "--voice", voice_entry["voice_id"],
                        "--text", script,
                        "--rate", rate,
                        "--write-media", str(audio_path),
                        "--write-subtitles", str(srt_path)
                    ]
                    try:
                        subprocess.run(tts_cmd, check=True, timeout=120)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError("Edge-TTS 在线语音合成超时（超过 120 秒），请检查网络连接后重试")

                # 2. 净化 SRT 格式并执行【V3.0+ 分镜级时间轴硬锚定】，彻底消除滚雪球抢跑/延后
                bilingual_applied = False
                bilingual_warning = ""
                use_ass_file = False
                actual_v_dur = get_video_duration(video_path)
                align_res = {}
                req_phases = data.get("phases")
                if srt_path.exists():
                    raw_srt = srt_path.read_text(encoding="utf-8")
                    cleaned_srt = sanitize_srt(raw_srt)
                    srt_path.write_text(cleaned_srt, encoding="utf-8")

                    phase_lock = bool(data.get("phaseLock", True))
                    if phase_lock and cleaned_srt.strip():
                        if not isinstance(req_phases, list) or not req_phases:
                            req_phases = analyze_telemetry_phases(
                                extract_openscreen_beats(video_path),
                                actual_v_dur,
                                video_path=video_path
                            )
                        align_res = align_tts_to_phases(
                            audio_path=audio_path,
                            srt_path=srt_path,
                            script=script,
                            phases=req_phases,
                            total_duration=actual_v_dur
                        )
                        if align_res.get("aligned"):
                            cleaned_srt = srt_path.read_text(encoding="utf-8")

                    # 2.5 若开启双语字幕，调用当前绑定的 AI 大模型生成双语 SRT 与分级排版 ASS
                    if bilingual_subs and cleaned_srt.strip():
                        bilingual_srt, bilingual_items, bi_warn = translate_srt_bilingual(
                            cleaned_srt,
                            target_lang=target_lang,
                            bilingual_order=bilingual_order
                        )
                        bilingual_warning = bi_warn
                        has_any_trans = any(it.get("secondary") for it in bilingual_items)
                        if has_any_trans:
                            srt_path.write_text(bilingual_srt, encoding="utf-8")
                            bilingual_applied = True
                            if burn_subs:
                                ass_content = build_bilingual_ass(
                                    bilingual_items,
                                    font_name=get_subtitle_font(),
                                    font_size=font_size,
                                    margin_v=max(14, margin_v - 4)
                                )
                                ass_path.write_text(ass_content, encoding="utf-8")
                                use_ass_file = True

                # 3. 计算物理音画时长与画面末尾定格延长保底 (杜绝配音未完画面被切断)
                actual_v_dur = get_video_duration(video_path)
                actual_a_dur = get_video_duration(audio_path)

                # 解析【V3.2 区间隐私高斯模糊】规则（归一化坐标 0~1：x, y, w, h, start, end）
                raw_blurs = data.get("privacyBlurs") or []
                blur_zones = []
                if isinstance(raw_blurs, list):
                    for bz in raw_blurs:
                        try:
                            b_st = max(0.0, float(bz.get("start", 0)))
                            b_ed = max(b_st + 0.1, float(bz.get("end", actual_v_dur)))
                            bx = max(0.0, min(0.98, float(bz.get("x", 0.3))))
                            by = max(0.0, min(0.98, float(bz.get("y", 0.3))))
                            bw = max(0.02, min(1.0 - bx, float(bz.get("w", 0.2))))
                            bh = max(0.02, min(1.0 - by, float(bz.get("h", 0.2))))
                            blur_zones.append({"start": b_st, "end": b_ed, "x": bx, "y": by, "w": bw, "h": bh})
                        except Exception:
                            continue

                v_filters = []
                if hold_last_frame and actual_a_dur > actual_v_dur:
                    pad_dur = round(actual_a_dur - actual_v_dur + 0.5, 2)
                    v_filters.append(f"tpad=stop_mode=clone:stop_duration={pad_dur}")

                # FFmpeg 压制合成 (双语优先使用分级排版 ASS；单语保持紧凑黑底样式)
                sub_filter_str = ""
                if burn_subs and use_ass_file and ass_path.exists():
                    escaped_ass = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
                    sub_filter_str = f"subtitles='{escaped_ass}'"
                elif burn_subs and srt_path.exists():
                    escaped_srt = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
                    sub_font = get_subtitle_font()
                    sub_filter_str = (
                        f"subtitles='{escaped_srt}':force_style="
                        f"'Fontname={sub_font},FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H75000000,"
                        f"BackColour=&H75000000,BorderStyle=3,Outline=2.5,Shadow=0,MarginV={margin_v}'"
                    )

                if blur_zones:
                    # 使用 filter_complex 串联任意个区间局部高斯模糊 + 字幕烧录（单次压制无损画质）
                    fc_parts = []
                    prev_lbl = "[0:v]"
                    if v_filters:
                        fc_parts.append(f"{prev_lbl}{','.join(v_filters)}[vbase]")
                        prev_lbl = "[vbase]"
                    for b_i, bz in enumerate(blur_zones):
                        en = f"between(t,{bz['start']:.2f},{bz['end']:.2f})"
                        fc_parts.append(f"{prev_lbl}split[bm{b_i}][bc{b_i}]")
                        fc_parts.append(
                            f"[bc{b_i}]crop=iw*{bz['w']:.4f}:ih*{bz['h']:.4f}:iw*{bz['x']:.4f}:ih*{bz['y']:.4f},gblur=sigma=24[bl{b_i}]"
                        )
                        next_lbl = f"[vb{b_i}]"
                        fc_parts.append(
                            f"[bm{b_i}][bl{b_i}]overlay=W*{bz['x']:.4f}:H*{bz['y']:.4f}:enable='{en}'{next_lbl}"
                        )
                        prev_lbl = next_lbl
                    if sub_filter_str:
                        fc_parts.append(f"{prev_lbl}{sub_filter_str}[vout]")
                        prev_lbl = "[vout]"
                    ff_cmd = [
                        "ffmpeg", "-y",
                        "-i", str(video_path),
                        "-i", str(audio_path),
                        "-filter_complex", ";".join(fc_parts),
                        "-map", prev_lbl,
                        "-map", "1:a:0",
                        "-c:v", "libx264",
                        "-preset", "veryfast",
                        "-crf", "20",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-af", "apad",
                        "-shortest",
                        str(final_video)
                    ]
                else:
                    if sub_filter_str:
                        v_filters.append(sub_filter_str)
                    combined_vf = ",".join(v_filters)
                    if combined_vf:
                        ff_cmd = [
                            "ffmpeg", "-y",
                            "-i", str(video_path),
                            "-i", str(audio_path),
                            "-vf", combined_vf,
                            "-c:v", "libx264",
                            "-preset", "veryfast",
                            "-crf", "20",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-af", "apad",
                            "-map", "0:v:0",
                            "-map", "1:a:0",
                            "-shortest",
                            str(final_video)
                        ]
                    else:
                        ff_cmd = [
                            "ffmpeg", "-y",
                            "-i", str(video_path),
                            "-i", str(audio_path),
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-af", "apad",
                            "-map", "0:v:0",
                            "-map", "1:a:0",
                            "-shortest",
                            str(final_video)
                        ]

                ff_timeout = max(600, min(2400, int(max(actual_v_dur, actual_a_dur) * 3.5)))
                try:
                    subprocess.run(ff_cmd, check=True, timeout=ff_timeout)
                except subprocess.TimeoutExpired:
                    raise RuntimeError(f"FFmpeg 视频渲染合成超时（超过 {ff_timeout} 秒）")

                # 4. 【V3.2 导出后音画卡点自检报告 & 分镜九宫格拼图】
                phase_metrics = align_res.get("phase_metrics") or []
                check_grid_path = OUTPUT_DIR / f"checkgrid_{run_id}.jpg"
                grid_url = ""
                if phase_metrics:
                    grid_res = generate_sync_check_grid(final_video, phase_metrics, check_grid_path)
                    if grid_res.get("generated"):
                        grid_url = f"/media?path={urllib.parse.quote(str(check_grid_path))}"

                # 5. 【V3.2 历史项目快照持久化】便于工作台左上角一键回载复现现场
                try:
                    proj_snapshot = {
                        "runId": run_id,
                        "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "videoPath": str(video_path),
                        "videoName": video_path.name,
                        "finalVideoPath": str(final_video),
                        "finalVideoUrl": f"/media?path={urllib.parse.quote(str(final_video))}",
                        "audioUrl": f"/media?path={urllib.parse.quote(str(audio_path))}",
                        "srtUrl": f"/media?path={urllib.parse.quote(str(srt_path))}",
                        "gridUrl": grid_url,
                        "script": script,
                        "voiceKey": voice_key,
                        "rate": rate,
                        "burnSubs": burn_subs,
                        "bilingualSubs": bilingual_subs,
                        "targetLang": target_lang,
                        "bilingualOrder": bilingual_order,
                        "phases": req_phases if isinstance(req_phases, list) else [],
                        "privacyBlurs": blur_zones,
                        "phaseMetrics": phase_metrics
                    }
                    (OUTPUT_DIR / f"project_{run_id}.json").write_text(
                        json.dumps(proj_snapshot, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                except Exception:
                    pass

                resp = {
                    "success": True,
                    "videoUrl": f"/media?path={urllib.parse.quote(str(final_video))}",
                    "videoName": final_video.name,
                    "audioUrl": f"/media?path={urllib.parse.quote(str(audio_path))}",
                    "srtUrl": f"/media?path={urllib.parse.quote(str(srt_path))}",
                    "gridUrl": grid_url,
                    "phaseMetrics": phase_metrics,
                    "bilingualApplied": bilingual_applied,
                    "bilingualWarning": bilingual_warning
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
                return
            else:
                self.send_error(404, "Endpoint Not Found")
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e), "message": str(e)}, ensure_ascii=False).encode("utf-8"))

def main():
    target_port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = None
    actual_port = target_port

    for p in range(target_port, target_port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), WorkbenchHandler)
            actual_port = p
            break
        except OSError:
            continue

    if not server:
        print(f"❌ 错误: 端口 {target_port}~{target_port+9} 均被占用，请指定其他可用端口。")
        sys.exit(1)

    url = f"http://localhost:{actual_port}"
    print(f"\n=======================================================")
    print(f"🎬 OpenScreen Studio · 软件教程自动化工作台已启动!")
    print(f"👉 访问地址: {url}")
    print(f"=======================================================\n")

    import webbrowser
    def _open_browser():
        time.sleep(1.0)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n工作台已停止。")

if __name__ == "__main__":
    main()
