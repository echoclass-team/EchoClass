"""LLM-based lesson metadata extractor.

调用 LLM（ChatECNU ecnu-max）从教案纯文本中抽取结构化元数据：
subject / grade / topic / objectives / key_points / difficult_points。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from llm.client import LLMClient
from schemas.lesson import LessonMeta

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


async def extract_lesson_meta(
    llm: LLMClient,
    text: str,
    *,
    max_chars: int = 8000,
) -> LessonMeta:
    """调用 LLM 从教案文本中抽取结构化元数据。

    Parameters
    ----------
    llm : LLMClient
        已配置好的 LLM 客户端。
    text : str
        教案纯文本（由 parser 产出）。
    max_chars : int
        发送给 LLM 的最大字符数，防止超出 token 上限。

    Returns
    -------
    LessonMeta
        抽取的结构化元数据。
    """
    truncated = text[:max_chars]

    template = _jinja_env.get_template("extractor.j2")
    prompt = template.render(lesson_text=truncated)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "请抽取上述教案的结构化信息。"},
    ]

    resp = await llm.chat(messages, temperature=0.0)
    raw = resp.choices[0].message.content or ""

    logger.debug("Extractor raw LLM output: %s", raw[:500])

    return _parse_meta(raw)


def _parse_meta(raw: str) -> LessonMeta:
    """从 LLM 原始输出中提取 JSON 并解析为 LessonMeta。"""
    # 尝试提取 markdown code block 中的 JSON
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 直接尝试找 { ... }
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            raise ValueError(f"No JSON found in extractor output: {raw[:200]}")

    # 预处理：清理 LaTeX 反斜杠（\lim, \Delta 等）和内嵌 ASCII 引号
    cleaned = _escape_lone_backslashes(json_str)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 兜底：LLM 有时在 JSON 字符串 value 内部保留了 ASCII 双引号（如 "掌握"凑十法"算理"）破坏结构。
        # 用中文引号替换 value 内部的游离 ASCII 引号后再试一次。
        fixed = _fix_embedded_quotes(cleaned)
        try:
            data = json.loads(fixed)
            logger.warning("extractor JSON 需要引号兜底修复后才能解析")
        except json.JSONDecodeError as exc:
            logger.error("JSON 解析失败，LLM 原始输出（前 2000 字）:\n%s", raw[:2000])
            raise ValueError(
                f"extractor JSON 解析失败: {exc}; raw 前 300 字: {raw[:300]}"
            ) from exc
    return LessonMeta(**data)


# 合法 JSON 转义字符集（\" \\ \/ \b \f \n \r \t \uXXXX）
_VALID_JSON_ESCAPES = set('"\\/' + "bfnrtu")


def _escape_lone_backslashes(s: str) -> str:
    """将非法 JSON 转义的反斜杠替换为双反斜杠。

    LLM 输出中常含 LaTeX 片段如 $\\lim$、$\\Delta$，其中的 \\l、\\D
    不是合法 JSON 转义，会导致 json.loads 报 Invalid \\escape 错误。
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            nxt = s[i + 1]
            if nxt in _VALID_JSON_ESCAPES:
                # 合法转义，保持原样
                out.append(s[i])
                out.append(nxt)
                i += 2
            else:
                # 非法转义 → 双反斜杠
                out.append("\\\\")
                i += 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _fix_embedded_quotes(s: str) -> str:
    """把 JSON 字符串 value 内部的游离 ASCII 双引号替换为中文引号。

    策略：逐字符扫描，跟踪是否在 value 字符串内（由 `: "` 或 `, "` 或 `[ "` 等结构进入）。
    进入后，除非遇到结束引号（后面紧跟 `,` / `]` / `}` / 换行 + 空白 + 结构符），
    否则字符串中间出现的 `"` 视为原文引号，替换成 U+201C / U+201D（交替使用）。
    """
    out: list[str] = []
    i = 0
    n = len(s)
    in_string = False
    while i < n:
        ch = s[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
                quote_toggle = 0  # 0 → 用左引号，1 → 右引号
            i += 1
            continue

        # in_string 内部：判断当前 `"` 是字符串真正的结束还是原文里的 ASCII 引号
        if ch == '"':
            # 向后找最近非空白
            k = i + 1
            while k < n and s[k] in " \t\r\n":
                k += 1
            next_nonspace = s[k] if k < n else ""
            # 结束引号的 next_nonspace 应该是 , } ] 或 : （: 对应 key 的结束）
            if next_nonspace in ",]}:":
                out.append(ch)
                in_string = False
                i += 1
                continue
            # 否则视为原文里的 ASCII 引号 → 用中文引号替换
            out.append("\u201c" if quote_toggle == 0 else "\u201d")
            quote_toggle = 1 - quote_toggle
            i += 1
            continue

        # 处理转义
        if ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(s[i + 1])
            i += 2
            continue

        out.append(ch)
        i += 1

    return "".join(out)
