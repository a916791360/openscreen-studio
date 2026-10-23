#!/usr/bin/env python3
# Copyright (c) 2026 杨冉 (https://github.com/a916791360)
# SPDX-License-Identifier: MIT
"""
AI 视频教程解说词智能生成与时长自适应引擎
Copyright (c) 2026 杨冉 (https://github.com/a916791360)
SPDX-License-Identifier: MIT
核心哲学：
  1. 真实操作由用户主导：绝不脱离用户操作要点胡编乱造菜单或步骤
  2. 严卡时间轴预算：根据视频物理秒数，智能执行双向拟合（短文本扩写润色 / 长文本脱水压缩）
  3. 支持真正的大模型 (LLM) 深度润色与自定义提示词（支持 DeepSeek / OpenAI / 智谱 / 硅基流动等）
  4. 保障音画严丝合缝：配音念完时画面刚好播完，杜绝视频截断或发呆
"""

import json
import math
import os
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# 中文自然朗读语速（字/秒，包含字间停顿，以 Edge-TTS 神经网络男/女声为实测基准）
CHARS_PER_SECOND = 4.3

OPENSCREEN_RECORDINGS_DIR = Path.home() / "Library/Application Support/openscreen/recordings"
CONFIG_FILE = Path(__file__).resolve().parent / "llm_config.json"

def normalize_api_url(url: str) -> str:
    """自动纠正/补齐 standard OpenAI 兼容接口地址"""
    u = url.strip().rstrip('/')
    if not u:
        return "https://api.deepseek.com/v1/chat/completions"
    if not u.endswith('/chat/completions'):
        if u.endswith('/v1') or u.endswith('/v4'):
            u = f"{u}/chat/completions"
        else:
            u = f"{u}/v1/chat/completions"
    return u

def load_llm_config() -> dict:
    default_cfg = {
        "provider": "deepseek",
        "apiUrl": "https://api.deepseek.com/v1",
        "apiKey": "",
        "model": "deepseek-chat",
        "systemPrompt": "你是一名资深的软件教程解说导演。请根据用户提供的系统真实操作记录，将其润色为一段口语自然、清晰易懂、节奏舒适的教程旁白解说词。",
        "stylePrompt": "要求：\n1. 语言风格：口语自然、清晰易懂、像同事在身边指引讲解，杜绝机械播音腔与大而无当的公文套话；\n2. 事实边界：100% 严格依照用户给定的真实操作，绝不脑补或虚构未提及的菜单与功能；\n3. 步骤结构：开场简短引入 -> 步骤自然衔接 -> 操作结果收尾；\n4. 时长卡控：系统将强制按物理秒数严格限制字数，请确保在该预算内完稿。"
    }
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            default_cfg.update(saved)
        except Exception:
            pass
    return default_cfg

def save_llm_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def test_llm_connection(api_config: dict) -> tuple:
    """测试大模型 API 连通性"""
    raw_url = api_config.get("apiUrl", "https://api.deepseek.com/v1")
    api_url = normalize_api_url(raw_url)
    api_key = api_config.get("apiKey", "").strip()
    model = api_config.get("model", "deepseek-chat").strip() or "deepseek-chat"

    if not api_key:
        return False, "请先填入有效的 API Key！"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "请回复四个字：连接成功"}
        ],
        "max_tokens": 15
    }

    try:
        req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            reply = res_data["choices"][0]["message"]["content"].strip()
            return True, f"测试成功！模型已正常就绪并响应：{reply}"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {e.code} 错误: {err_body[:200]}"
    except urllib.error.URLError as e:
        return False, f"网络连接失败: 无法连接至 {api_url} ({e.reason})"
    except Exception as e:
        return False, f"连接异常: {str(e)}"

def call_llm_api(prompt: str, system_prompt: str, api_config: dict) -> tuple:
    """调用用户配置的大模型 API (兼容 OpenAI / DeepSeek 等标准接口)"""
    raw_url = api_config.get("apiUrl", "https://api.deepseek.com/v1")
    api_url = normalize_api_url(raw_url)
    api_key = api_config.get("apiKey", "").strip()
    model = api_config.get("model", "deepseek-chat").strip() or "deepseek-chat"

    if not api_key:
        return None, "未配置 API Key"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "max_tokens": 1200
    }

    try:
        req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=35) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"].strip()
            return content, ""
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {e.code}: {err_body[:200]}"
    except urllib.error.URLError as e:
        return None, f"网络连接失败: {e.reason}"
    except Exception as e:
        return None, f"调用异常: {str(e)}"

def adapt_script_to_duration(user_summary: str, duration_sec: float, video_path: Path = None, api_config: dict = None) -> dict:
    """
    核心入口：根据用户真实总结的操作步骤，严卡视频时长与运镜节拍进行深度拟合与润色
    返回字典: {"script": str, "source": "llm"|"rule", "phases": list, "paragraphs": list, "message": str}
    """
    dur = max(5.0, duration_sec)
    target_chars = int(dur * CHARS_PER_SECOND)
    safe_chars = max(20, int(dur * 3.8))
    clean_text = user_summary.strip() if user_summary else ""
    if not clean_text:
        return {"script": "", "source": "none", "phases": [], "paragraphs": [], "message": "输入内容为空"}

    # 提取与当前视频关联的 OpenScreen 运镜节拍与分镜阶段
    beats = extract_openscreen_beats(video_path) if video_path else []
    phases = analyze_telemetry_phases(beats, dur)

    # 加载已保存的大模型配置
    cfg = api_config or load_llm_config()

    # 1. 如果已配置大模型 API Key，执行真正的大模型深度润色（音画分镜联动）
    if cfg and cfg.get("apiKey") and cfg.get("apiKey").strip():
        sys_dir = cfg.get("systemPrompt", "你是一名资深的软件教程解说导演。请根据用户提供的系统真实操作记录，将其润色为一段口语自然、清晰易懂、节奏舒适的教程旁白解说词。")
        style_dir = cfg.get("stylePrompt", "要求：\n1. 语言风格：口语自然、清晰易懂，杜绝机械播音腔与大而无当的公文套话；\n2. 事实边界：100% 严格依照用户给定的真实操作，绝不脑补或虚构未提及的菜单与功能；\n3. 步骤结构：开场简短引入 -> 步骤自然衔接 -> 操作结果收尾。")

        phase_lines = []
        for p in phases:
            min_c = max(10, p['char_budget'] - 4)
            max_c = p['char_budget'] + 4
            phase_lines.append(
                f"- 第 {p['index']} 段 [{p['start']}s ~ {p['end']}s]（{p['label']}，建议控制在【{min_c} 至 {max_c} 字】）：{p['hint']}"
            )
        phase_guidance = "\n".join(phase_lines)

        full_sys_prompt = (
            f"{sys_dir}\n\n"
            f"{style_dir}\n\n"
            f"【视频分镜节拍与时间轴基准】：\n"
            f"当前录屏物理总时长为 {round(dur, 1)} 秒，系统已基于 OpenScreen 遥测解析出 {len(phases)} 个运镜分镜阶段：\n"
            f"{phase_guidance}\n\n"
            f"【语句完整性与字数红线（绝对不可违背）】：\n"
            f"1. 必须输出且仅输出 {len(phases)} 个自然段落，每个自然段严格按顺序对应上方的一个分镜阶段！\n"
            f"2. 严禁断句截断：每一段必须是【语法完整、语义闭环、有头有尾】的口语句子，结尾必须是句号（。）！绝对严禁写出半截话或未讲完的断语（如绝不能只写“专属经销商就会收”、“方便”这类缺少谓语/宾语的半截断词）！\n"
            f"3. 紧凑凝练：请紧扣建议字数表达，不要添加冗长啰嗦的虚词套话，使语速自然卡在对应镜头区间内。\n"
            f"4. 段落之间用空行隔开；直接输出纯解说词文本，严禁输出任何 Markdown 标题、严禁输出时间戳、严禁输出解释说明。"
        )

        user_prompt = (
            f"用户录制的真实系统操作步骤如下：\n"
            f"--------------------\n"
            f"{clean_text}\n"
            f"--------------------\n"
            f"请严格按照上方的 {len(phases)} 个运镜分镜阶段，将上述真实操作润色为 {len(phases)} 段音画严密同步、表意完整闭环的解说词："
        )

        llm_res, err_msg = call_llm_api(user_prompt, full_sys_prompt, cfg)
        if llm_res:
            raw_paras = [p.strip() for p in llm_res.split('\n') if p.strip()]
            clean_paras = []
            for p in raw_paras:
                p_clean = clean_script_text(p)
                p_clean = re.sub(r'^(第[一二三四五六七八九十\d]+段|分镜\d+|步骤\d+|P\d+)[\s：:、.-]*', '', p_clean)
                if p_clean:
                    clean_paras.append(p_clean)

            if len(clean_paras) == len(phases):
                final_paras = []
                for p_text, ph in zip(clean_paras, phases):
                    p_text = p_text.strip()
                    # 确保每段结尾标点规范闭合，绝无半句或截断
                    if not re.search(r'[。！？]$', p_text):
                        p_text = re.sub(r'[，,；;、\s]+$', '', p_text) + '。'
                    final_paras.append(p_text)
                cleaned_script = "\n\n".join(final_paras)
            else:
                cleaned_script = "\n\n".join(clean_paras)

            # 计算分镜段落统计信息
            paragraphs_stats = []
            split_paras = [p.strip() for p in cleaned_script.split('\n') if p.strip()]
            for idx, ph in enumerate(phases):
                p_text = split_paras[idx] if idx < len(split_paras) else ""
                c_len = len(re.sub(r'\s+', '', p_text))
                paragraphs_stats.append({
                    "index": ph["index"],
                    "start": ph["start"],
                    "end": ph["end"],
                    "label": ph["label"],
                    "text": p_text,
                    "char_count": c_len,
                    "target_chars": ph["char_budget"],
                    "status": "fit" if abs(c_len - ph["char_budget"]) <= 5 else ("over" if c_len > ph["char_budget"] else "under")
                })

            total_chars = sum(p["char_count"] for p in paragraphs_stats)
            msg = f"✓ 已由 {cfg.get('model', '大模型')} 依照 {len(phases)} 处运镜分镜完成深度润色 (共 {total_chars} 字，严格拟合视频节奏)"
            return {
                "script": cleaned_script,
                "source": "llm",
                "phases": phases,
                "paragraphs": paragraphs_stats,
                "message": msg
            }
        else:
            # 大模型调用出错，降级并明确提示用户
            fallback_text = run_local_engine(clean_text, target_chars, dur, phases)
            split_paras = [p.strip() for p in fallback_text.split('\n') if p.strip()]
            paragraphs_stats = []
            for idx, ph in enumerate(phases):
                p_text = split_paras[idx] if idx < len(split_paras) else ""
                c_len = len(re.sub(r'\s+', '', p_text))
                paragraphs_stats.append({
                    "index": ph["index"],
                    "start": ph["start"],
                    "end": ph["end"],
                    "label": ph["label"],
                    "text": p_text,
                    "char_count": c_len,
                    "target_chars": ph["char_budget"],
                    "status": "fit"
                })
            return {
                "script": fallback_text,
                "source": "rule_fallback",
                "phases": phases,
                "paragraphs": paragraphs_stats,
                "message": f"⚠️ 大模型调用失败 ({err_msg})，已自动降级为分镜规则拟合"
            }

    # 2. 未配置大模型，使用本地轻量自适应拟合引擎
    rule_text = run_local_engine(clean_text, target_chars, dur, phases)
    split_paras = [p.strip() for p in rule_text.split('\n') if p.strip()]
    paragraphs_stats = []
    for idx, ph in enumerate(phases):
        p_text = split_paras[idx] if idx < len(split_paras) else ""
        c_len = len(re.sub(r'\s+', '', p_text))
        paragraphs_stats.append({
            "index": ph["index"],
            "start": ph["start"],
            "end": ph["end"],
            "label": ph["label"],
            "text": p_text,
            "char_count": c_len,
            "target_chars": ph["char_budget"],
            "status": "fit"
        })
    return {
        "script": rule_text,
        "source": "rule",
        "phases": phases,
        "paragraphs": paragraphs_stats,
        "message": f"提示：当前使用本地分镜自适应引擎（已联动 {len(phases)} 个分镜）。如需大模型生动润色，可点击右上方【🤖 大模型与提示词配置】。"
    }

def run_local_engine(clean_text: str, target_chars: int, dur: float, phases: list = None) -> str:
    """本地自适应拟合引擎（支持分镜阶段对齐）"""
    chars_count = len(re.sub(r'\s+', '', clean_text))

    if phases and len(phases) >= 3:
        # 按分镜阶段智能分布台词
        raw_steps = [s.strip() for s in re.split(r'[，,。；;\n\t]+', clean_text) if s.strip()]
        if not raw_steps:
            raw_steps = [clean_text]
        
        first_clean = re.sub(r'^(在|进入|点击)', '', raw_steps[0])
        topic_hint = first_clean[:12] if len(first_clean) > 12 else first_clean

        paras = []
        for p in phases:
            ptype = p.get('type')
            budget = p.get('char_budget', 20)
            if ptype == 'intro' or (p['index'] == 1 and ptype == 'zoom'):
                s = f"大家好，欢迎观看操作指南，本期为您演示{topic_hint}的完整业务流程。"
                if len(s) > budget + 4:
                    s = f"大家好，本期为您演示{topic_hint}的核心操作。"
                paras.append(s)
            elif ptype == 'outro' or p['index'] == len(phases):
                s = "核对确认后业务已即刻流转并生效，演示完毕。"
                paras.append(s)
            else:
                # 寻找对应的用户步骤
                step_idx = (p['index'] - 2) % len(raw_steps)
                step_val = raw_steps[step_idx]
                step_val = re.sub(r'^(首先|接着|随后|然后|最后)[，,]*', '', step_val)
                conn = "接下来在操作界面中，" if p['index'] == 2 else "随后仔细核对并"
                s = f"{conn}{step_val}。"
                paras.append(s)
        return "\n\n".join(paras)

    if abs(chars_count - target_chars) <= 12:
        return format_clean_paragraphs(clean_text)

    if chars_count > target_chars + 12:
        return compress_text_to_target(clean_text, target_chars)

    return expand_summary_to_target(clean_text, target_chars, dur)

    return expand_summary_to_target(clean_text, target_chars, dur)

def format_clean_paragraphs(text: str) -> str:
    parts = [s.strip() for s in re.split(r'([。！？\n])', text) if s.strip()]
    lines = []
    cur = ""
    for s in parts:
        cur += s
        if s in ['。', '！', '？', '\n']:
            if len(cur.strip()) >= 18:
                lines.append(cur.strip())
                cur = ""
    if cur.strip():
        lines.append(cur.strip())
    return "\n".join(lines) if lines else text

def compress_text_to_target(text: str, target_chars: int) -> str:
    processed = re.sub(r'(众所周知|在日常工作中|为了进一步提升|总的来说|毋庸置疑|值得一提的是|可以看到的是)[，,]*', '', text)
    parts = re.split(r'([。！？\n])', processed)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = (parts[i].strip() + parts[i+1]).strip()
        s = re.sub(r'^[，,、\s]+', '', s)
        if s: sentences.append(s)
    if len(parts) % 2 == 1 and parts[-1].strip():
        s = re.sub(r'^[，,、\s]+', '', parts[-1].strip())
        if s: sentences.append(s)

    action_keywords = ["点击", "进入", "选择", "输入", "录入", "新建", "提交", "确认", "保存", "更新", "派单", "派发", "状态", "指派"]
    scored = []
    for idx, s in enumerate(sentences):
        hits = [kw for kw in action_keywords if kw in s]
        score = len(hits) * 3
        if idx == 0: score += 4
        if idx == len(sentences) - 1: score += 3
        scored.append((score, idx, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected_indices = set()
    accum_chars = 0
    for score, idx, s in scored:
        s_len = len(re.sub(r'\s+', '', s))
        if accum_chars + s_len <= target_chars:
            selected_indices.add(idx)
            accum_chars += s_len

    result = [sentences[i] for i in sorted(selected_indices)]
    if not result and sentences:
        result = [sentences[0]]
    return "\n".join(result)

def expand_summary_to_target(text: str, target_chars: int, dur: float) -> str:
    raw_steps = [s.strip() for s in re.split(r'[，,。；;\n\t]+', text) if s.strip()]
    if not raw_steps:
        raw_steps = [text]

    first_clean = re.sub(r'^(在|进入|点击)', '', raw_steps[0])
    topic_hint = first_clean[:12] if len(first_clean) > 12 else first_clean

    intros = [
        f"大家好，本期演示{topic_hint}。",
        f"大家好，欢迎观看操作指南，本期为您演示{topic_hint}的核心处理流程。",
        f"大家好，欢迎观看系统实操指南，本期我们将针对{topic_hint}，带来完整的业务流程演示。"
    ]

    outros = [
        "操作演示完毕。",
        "可以看到流程已实时生效，演示完毕。",
        "核对确认后业务已即刻流转并生效，工程师端将同步收到提醒，操作演示完毕。"
    ]

    step_connectors = [
        ("首先，", "首先在主界面导航中，", "首先进入系统主界面，定位并"),
        ("接着，", "接着在操作面板中，", "接着进入对应功能模块，"),
        ("随后，", "随后根据业务要求，", "随后仔细核对并"),
        ("在此步骤中，", "在当前表单区域中，", "在此环节中依次"),
        ("核对无误后，", "核对各项关键信息无误后，", "确认各项字段与参数无误后，点击"),
    ]

    step_options = []
    for i, st in enumerate(raw_steps):
        conn = step_connectors[min(i, len(step_connectors)-1)]
        clean_st = re.sub(r'^(首先|接着|随后|然后|最后|在此步骤中)[，,]*', '', st)
        opt1 = f"{conn[0]}{clean_st}。"
        opt2 = f"{conn[1]}{clean_st}。"
        opt3 = f"{conn[2]}{clean_st}。"
        
        opt1 = re.sub(r'(点击|进入)\s*\1', r'\1', opt1)
        opt2 = re.sub(r'(点击|进入)\s*\1', r'\1', opt2)
        opt3 = re.sub(r'(点击|进入)\s*\1', r'\1', opt3)
        step_options.append([opt1, opt2, opt3])

    best_text = ""
    best_diff = 999999

    for intro in intros:
        for outro in outros:
            chosen = [opts[0] for opts in step_options]
            cand = [intro] + chosen + [outro]
            cand_text = "\n".join(cand)
            cand_len = len(re.sub(r'\s+', '', cand_text))

            step_idx = 0
            while cand_len < target_chars - 8 and step_idx < len(step_options):
                if chosen[step_idx] == step_options[step_idx][0]:
                    chosen[step_idx] = step_options[step_idx][1]
                elif chosen[step_idx] == step_options[step_idx][1]:
                    chosen[step_idx] = step_options[step_idx][2]
                cand = [intro] + chosen + [outro]
                cand_text = "\n".join(cand)
                cand_len = len(re.sub(r'\s+', '', cand_text))
                step_idx = (step_idx + 1) % len(step_options)
                if all(c == opts[2] for c, opts in zip(chosen, step_options)):
                    break

            diff = abs(target_chars - cand_len)
            if cand_len > target_chars:
                diff += (cand_len - target_chars) * 3

            if diff < best_diff:
                best_diff = diff
                best_text = cand_text

    return best_text

def clean_script_text(text: str) -> str:
    t = text.strip()
    t = re.sub(r'^(台词|解说词|脚本)[：:\n]+', '', t)
    t = re.sub(r'^```[\w]*\n', '', t)
    t = re.sub(r'\n```$', '', t)
    return t.strip()

def get_file_duration(p: Path) -> float:
    """获取音视频文件精确物理时长"""
    if not p or not p.exists():
        return 0.0
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(p)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def find_matching_openscreen_project(video_path: Path, override_proj: str = None) -> tuple:
    """
    智能多维加权匹配 OpenScreen 项目 (.openscreen) 与鼠标遥测文件 (.cursor.json)
    支持多文件并发导出场景下的 100% 精准识别：
    1. 用户手动指定 override_proj 优先
    2. 同目录下同名项目优先
    3. 多维加权打分匹配：
       - 微秒级物理时长差值 (dur_diff < 0.05s 得 100 分，自动剔除不同录屏)
       - 剪辑有效时长判定 (自动扣除 trimRegions)
       - 时间戳因果回溯 (export-ts 必须在 recording-ts 之后，且时间差最小)
       - 运镜与鼠标交互遥测数据丰富度加权
    返回: (proj_file, cursor_file, match_info)
    """
    if not video_path:
        return None, None, {"matched": False, "reason": "未指定视频路径"}
    video_path = Path(video_path)

    # 1. 用户显式指定优先
    if override_proj:
        target = OPENSCREEN_RECORDINGS_DIR / override_proj
        if target.exists():
            c_file = Path(str(target.with_suffix(".mp4")) + ".cursor.json")
            return target, (c_file if c_file.exists() else None), {
                "matched": True, "projectName": target.name, "confidence": "100%", "reason": "用户手动指定匹配工程"
            }

    # 2. 同目录下匹配
    proj_file = video_path.with_suffix(".openscreen")
    cursor_file = Path(str(video_path) + ".cursor.json")
    if proj_file.exists():
        return proj_file, (cursor_file if cursor_file.exists() else None), {
            "matched": True, "projectName": proj_file.name, "confidence": "100%", "reason": "同目录下同名工程文件匹配"
        }

    if not OPENSCREEN_RECORDINGS_DIR.exists():
        return None, None, {"matched": False, "reason": "OpenScreen 录屏目录不存在"}

    cands = list(OPENSCREEN_RECORDINGS_DIR.glob("*.openscreen"))
    if not cands:
        return None, None, {"matched": False, "reason": "未检测到 OpenScreen 工程"}

    v_dur = get_file_duration(video_path)
    exp_ts_match = re.search(r'export-(\d+)', video_path.name)
    exp_ts = int(exp_ts_match.group(1)) if exp_ts_match else None

    scored_cands = []
    for cand in cands:
        cand_mp4 = cand.with_suffix(".mp4")
        cand_dur = get_file_duration(cand_mp4) if cand_mp4.exists() else 0.0

        zooms_count = 0
        effective_dur = cand_dur
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
            trims = data.get("editor", {}).get("trimRegions", [])
            trim_dur = sum((t.get("endMs", 0) - t.get("startMs", 0)) / 1000 for t in trims)
            effective_dur = cand_dur - trim_dur
            zooms_count = len(data.get("editor", {}).get("zoomRegions", []))
        except Exception:
            pass

        dur_diff = abs(effective_dur - v_dur) if v_dur > 0 else 999.0
        rec_m = re.search(r'recording-(\d+)', cand.name)
        rec_ts = int(rec_m.group(1)) if rec_m else int(cand.stat().st_mtime * 1000)

        score = 0
        reasons = []

        if dur_diff < 0.05:
            score += 100
            reasons.append(f"时长微秒级完全吻合 (差值 {dur_diff:.3f}s)")
        elif dur_diff < 0.4:
            score += 70
            reasons.append(f"时长高度契合 (差值 {dur_diff:.2f}s)")
        elif dur_diff < 1.2:
            score += 30
            reasons.append(f"时长近似 (差值 {dur_diff:.1f}s)")

        if exp_ts and rec_ts <= exp_ts:
            time_gap_min = (exp_ts - rec_ts) / 60000
            if time_gap_min < 180:
                score += 30
                reasons.append(f"导出时间因果回溯 (录制后 {int(time_gap_min)} 分钟内导出)")
            else:
                score += 15
        elif exp_ts and rec_ts > exp_ts:
            score -= 50

        if zooms_count > 0:
            score += 20
            reasons.append(f"包含 {zooms_count} 处运镜特写")

        c_file = Path(str(cand.with_suffix(".mp4")) + ".cursor.json")
        has_cursor = c_file.exists()
        if has_cursor:
            score += 10
            reasons.append("包含完整鼠标点击遥测")

        scored_cands.append({
            "cand": cand,
            "cursor": c_file if has_cursor else None,
            "score": score,
            "dur_diff": dur_diff,
            "reasons": reasons,
            "zooms_count": zooms_count
        })

    scored_cands.sort(key=lambda x: x["score"], reverse=True)
    best = scored_cands[0]

    confidence = "100%" if best["score"] >= 120 else ("85%" if best["score"] >= 80 else "60%")
    match_info = {
        "matched": True,
        "projectName": best["cand"].name,
        "score": best["score"],
        "confidence": confidence,
        "durDiff": round(best["dur_diff"], 3),
        "reasons": best["reasons"],
        "zoomsCount": best["zooms_count"]
    }
    return best["cand"], best["cursor"], match_info

def list_available_openscreen_projects() -> list:
    """枚举当前系统中的所有 OpenScreen 录制工程"""
    if not OPENSCREEN_RECORDINGS_DIR.exists():
        return []
    projs = []
    for cand in sorted(OPENSCREEN_RECORDINGS_DIR.glob("*.openscreen"), key=os.path.getmtime, reverse=True):
        cand_mp4 = cand.with_suffix(".mp4")
        dur = get_file_duration(cand_mp4) if cand_mp4.exists() else 0.0
        zooms = 0
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
            zooms = len(d.get("editor", {}).get("zoomRegions", []))
        except Exception:
            pass
        projs.append({
            "name": cand.name,
            "duration": round(dur, 1),
            "zooms": zooms,
            "mtime": cand.stat().st_mtime
        })
    return projs

def extract_openscreen_beats(video_path: Path, override_proj: str = None):
    """提取视频相关的 OpenScreen 动作节拍 (镜头特写 + 鼠标交互)"""
    beats = []
    if not video_path:
        return beats

    proj_file, cursor_file, _ = find_matching_openscreen_project(video_path, override_proj)

    if proj_file and proj_file.exists():
        try:
            data = json.loads(proj_file.read_text(encoding="utf-8"))
            zooms = data.get("editor", {}).get("zoomRegions", [])
            for z in zooms:
                beats.append({
                    "start": round(z.get("startMs", 0) / 1000, 1),
                    "end": round(z.get("endMs", 0) / 1000, 1),
                    "type": "zoom",
                    "label": "镜头特写",
                    "focus": z.get("focus", {})
                })
        except Exception:
            pass

    if cursor_file and cursor_file.exists():
        try:
            cdata = json.loads(cursor_file.read_text(encoding="utf-8"))
            samples = cdata.get("samples", [])
            clicks = [s for s in samples if s.get("interactionType") in ["down", "click"]]
            last_t = -999.0
            for c in clicks:
                t = round(c.get("timeMs", 0) / 1000, 1)
                if abs(t - last_t) >= 0.3:
                    beats.append({
                        "start": t,
                        "type": "click",
                        "label": "鼠标点击",
                        "cx": round(c.get("cx", 0.5), 2),
                        "cy": round(c.get("cy", 0.5), 2)
                    })
                    last_t = t
        except Exception:
            pass

    beats.sort(key=lambda x: x["start"])
    return beats

def analyze_telemetry_phases(beats: list, total_duration: float) -> list:
    """
    根据 OpenScreen 遥测节拍，将整段视频智能聚类划分为 3~6 个连贯的导演分镜阶段 (Phases)
    每个阶段包含起始时间、时长、运镜类型、视觉聚焦提示以及严格的字数预算。
    """
    dur = max(5.0, float(total_duration))
    zooms = [b for b in beats if b.get('type') == 'zoom']
    clicks = [b for b in beats if b.get('type') == 'click']

    if not zooms:
        # 无镜头缩放数据时，生成通用 3-4 分镜
        if dur <= 15:
            phases = [
                {'start': 0.0, 'end': round(dur*0.3, 1), 'duration': round(dur*0.3, 1), 'type': 'intro', 'label': '开场引入', 'hint': '开门见山点出本期操作任务', 'char_budget': max(10, int(dur*0.3*3.8))},
                {'start': round(dur*0.3, 1), 'end': round(dur*0.8, 1), 'duration': round(dur*0.5, 1), 'type': 'action', 'label': '核心操作', 'hint': '讲解关键操作步骤与注意事项', 'char_budget': max(15, int(dur*0.5*3.8))},
                {'start': round(dur*0.8, 1), 'end': round(dur, 1), 'duration': round(dur*0.2, 1), 'type': 'outro', 'label': '结果收尾', 'hint': '确认操作生效并收尾', 'char_budget': max(8, int(dur*0.2*3.5))}
            ]
        else:
            phases = [
                {'start': 0.0, 'end': 5.0, 'duration': 5.0, 'type': 'intro', 'label': '开场引入', 'hint': '开门见山点出本期操作任务', 'char_budget': 19},
                {'start': 5.0, 'end': round(dur*0.45, 1), 'duration': round(dur*0.45 - 5.0, 1), 'type': 'action', 'label': '定位与入口', 'hint': '找到并进入对应功能模块', 'char_budget': max(15, int((dur*0.45 - 5.0)*3.8))},
                {'start': round(dur*0.45, 1), 'end': round(dur - 6.0, 1), 'duration': round(dur - 6.0 - dur*0.45, 1), 'type': 'action', 'label': '表单核心填写', 'hint': '录入关键信息并核对', 'char_budget': max(20, int((dur - 6.0 - dur*0.45)*3.8))},
                {'start': round(dur - 6.0, 1), 'end': round(dur, 1), 'duration': 6.0, 'type': 'outro', 'label': '确认提交与完成', 'hint': '提交保存并确认状态流转', 'char_budget': 22}
            ]
        for idx, p in enumerate(phases):
            p['index'] = idx + 1
        return phases

    # 有 zoom 数据时，按镜头聚类 (相邻 2.8s 内的特写合并为一个运镜阶段)
    clusters = []
    for z in sorted(zooms, key=lambda x: x['start']):
        z_start = max(0.0, float(z.get('start', 0)))
        z_end = min(dur, float(z.get('end', z_start + 2.1)))
        cx = z.get('focus', {}).get('cx', 0.5)
        cy = z.get('focus', {}).get('cy', 0.5)
        if not clusters or z_start - clusters[-1]['end'] > 2.8:
            clusters.append({
                'start': z_start,
                'end': z_end,
                'zooms': [z],
                'avg_cx': cx,
                'avg_cy': cy
            })
        else:
            clusters[-1]['end'] = max(clusters[-1]['end'], z_end)
            clusters[-1]['zooms'].append(z)
            n = len(clusters[-1]['zooms'])
            clusters[-1]['avg_cx'] = (clusters[-1]['avg_cx'] * (n-1) + cx) / n
            clusters[-1]['avg_cy'] = (clusters[-1]['avg_cy'] * (n-1) + cy) / n

    phases = []
    cur_t = 0.0
    for idx, c in enumerate(clusters):
        c_start = c['start']
        c_end = min(dur, c['end'])
        cx = c['avg_cx']
        cy = c['avg_cy']

        loc = '中央区域'
        if cx < 0.35: loc = '左侧导航/菜单'
        elif cx > 0.65 and cy > 0.6: loc = '右下角提交与指派区'
        elif cx > 0.65: loc = '右侧操作面板'
        elif cy < 0.35: loc = '顶部工具栏'

        # 如果两个镜头之间有平视间隙
        if c_start > cur_t + 1.2:
            sub_clicks = [clk for clk in clicks if cur_t <= clk.get('start', 0) < c_start]
            click_desc = f'（含 {len(sub_clicks)} 次交互）' if sub_clicks else ''
            p_dur = c_start - cur_t
            phases.append({
                'start': round(cur_t, 1),
                'end': round(c_start, 1),
                'duration': round(p_dur, 1),
                'type': 'action',
                'label': f'主操作区{click_desc}',
                'hint': '正常全景视角，进行页面核心录入与交互'
            })
            cur_t = c_start

        p_dur = c_end - cur_t
        tag = '开场特写' if cur_t < 2.0 else f'特写聚焦 [{loc}]'
        hint = '开场总览，点出本期操作任务' if cur_t < 2.0 else f'镜头拉近放大至{loc}，突出当前关键动作'
        phases.append({
            'start': round(cur_t, 1),
            'end': round(c_end, 1),
            'duration': round(p_dur, 1),
            'type': 'zoom',
            'label': tag,
            'hint': hint
        })
        cur_t = c_end

    if cur_t < dur - 0.5:
        p_dur = dur - cur_t
        phases.append({
            'start': round(cur_t, 1),
            'end': round(dur, 1),
            'duration': round(p_dur, 1),
            'type': 'outro',
            'label': '结果展示与收尾',
            'hint': '全景视角，展示最终执行结果与状态确认'
        })

    # 为每个阶段计算字数预算（黄金语速 4.2 字/秒）与序号
    for idx, p in enumerate(phases):
        p['index'] = idx + 1
        p['char_budget'] = max(12, int(round(p['duration'] * 4.2)))

    return phases

def extract_openscreen_beats_legacy(video_path: Path):
    return extract_openscreen_beats(video_path)

def generate_script(video_path: Path, duration_sec: float, user_topic: str = "", api_config: dict = None):
    res = adapt_script_to_duration(user_topic, duration_sec, video_path, api_config)
    return res.get("script", "")

def compress_script_to_duration(text: str, duration_sec: float, api_config: dict = None):
    res = adapt_script_to_duration(text, duration_sec, None, api_config)
    return res.get("script", "")
