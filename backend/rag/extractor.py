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

    data = json.loads(json_str)
    return LessonMeta(**data)
