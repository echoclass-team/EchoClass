"""学段 few-shot 示例集合加载模块。

`data/qa_examples/<stage_id>.json` 为每个学段提供 2 个 ask 范例 + 2 个 chat 范例，
用于注入到 student_ask.j2 / student_chat.j2 prompt 中显著提升 LLM 输出质量。

设计要点：
- 数据驱动：范例放 JSON，与代码解耦，便于 Role C / Role A 协作维护
- 学段索引：直接按 ``stage_id`` 加载，避免 prompt 里塞 6 学段全部范例造成 token 浪费
- ``lru_cache``：进程级缓存，避免每次 generate_questions 都读盘
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================== schemas


class QAExampleQuestion(BaseModel):
    """ask 范例中的单个问题。字段语义对齐 ``schemas.question.StudentQuestion``。"""

    content: str = Field(..., description="学生原话")
    category: str = Field(..., description="QuestionCategory 字符串")
    difficulty: str = Field(..., description="QuestionDifficulty 字符串")
    linked_key_point: str | None = Field(default=None)
    linked_misconception_id: str | None = Field(default=None)
    rationale: str = Field(default="", description="学生内心 OS")


class QAAskExample(BaseModel):
    """单个 ask 范例：一个 persona_tag 下的 2-3 个问题示范。"""

    persona_tag: str = Field(..., description="范例对应的人设类型，如 weak / xueba")
    topic: str = Field(..., description="范例使用的课题（仅作 prompt 上下文）")
    key_points: list[str] = Field(default_factory=list)
    questions: list[QAExampleQuestion] = Field(default_factory=list)


class QAChatTurn(BaseModel):
    """chat 范例中的单条对话消息。"""

    role: str = Field(..., description="teacher / student")
    content: str = Field(..., description="该轮发言原文")
    self_resolved: bool = Field(
        default=False,
        description="学生回应末尾是否带 [懂了] 标记（仅 role=student 有意义）",
    )


class QAChatExample(BaseModel):
    """单个对话范例：一个场景内的多轮 teacher/student 交互。"""

    persona_tag: str = Field(...)
    scenario: str = Field(..., description="简短场景说明")
    initial_question: str = Field(default="", description="学生最初的问题，可选")
    turns: list[QAChatTurn] = Field(default_factory=list)


class QAExampleSet(BaseModel):
    """单个学段的全部 few-shot 范例。"""

    stage_id: str
    stage_name: str
    ask_examples: list[QAAskExample] = Field(default_factory=list)
    chat_examples: list[QAChatExample] = Field(default_factory=list)


# =============================================================== loader


def _default_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "qa_examples"


@lru_cache(maxsize=8)
def _load_cached(qa_examples_dir: str, stage_id: str) -> QAExampleSet | None:
    """按 stage_id 加载示例集合；缺失时返回 None（caller 可降级）。"""
    path = Path(qa_examples_dir) / f"{stage_id}.json"
    if not path.exists():
        logger.warning("qa_examples: %s not found, fallback to no-shot", path)
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("qa_examples: failed to load %s: %s", path, exc)
        return None
    try:
        return QAExampleSet(**data)
    except Exception as exc:  # noqa: BLE001 - pydantic ValidationError 等
        logger.warning("qa_examples: invalid schema in %s: %s", path, exc)
        return None


def load_qa_examples(
    stage_id: str,
    qa_examples_dir: str | Path | None = None,
) -> QAExampleSet | None:
    """加载某学段的全部 few-shot 范例。

    Parameters
    ----------
    stage_id : str
        学段 id，对应 ``data/stage_profiles/*.json`` 与 ``data/qa_examples/<id>.json``。
    qa_examples_dir : path, optional
        覆盖默认目录。测试场景常用。

    Returns
    -------
    QAExampleSet | None
        当目录或文件缺失、或 schema 不合法时返回 None；上游应做降级（不注入 few-shot）。
    """
    directory = Path(qa_examples_dir) if qa_examples_dir is not None else _default_dir()
    return _load_cached(str(directory), stage_id)


def select_ask_examples(
    examples: QAExampleSet | None,
    *,
    persona_level: str = "",
    persona_tag_hint: str = "",
    max_count: int = 2,
) -> list[QAAskExample]:
    """从 ask_examples 里挑选最贴当前 persona 的范例。

    优先策略：
    1. 若 ``persona_tag_hint`` 非空且能精确匹配某条范例的 ``persona_tag``，则它优先
    2. 否则按 ``persona_level`` 关键字 fuzzy 匹配（"薄弱"/"weak"、"优秀"/"xueba" 等）
    3. 最后按文件中的顺序补足到 ``max_count``

    Returns
    -------
    list[QAAskExample]
        最多 max_count 条；若 examples 为 None 则返回空列表。
    """
    if examples is None:
        return []
    pool = list(examples.ask_examples)
    if not pool:
        return []

    selected: list[QAAskExample] = []
    seen: set[int] = set()

    if persona_tag_hint:
        for i, ex in enumerate(pool):
            if ex.persona_tag == persona_tag_hint:
                selected.append(ex)
                seen.add(i)
                break

    level_lower = persona_level.lower()
    keyword_map = {
        "weak": ["薄弱", "weak", "lost", "giveup"],
        "strong": ["优秀", "优等", "xueba", "top", "thinker", "striver", "mature"],
        "distracted": ["distracted", "restless", "offtopic", "off_topic", "走神"],
    }
    fuzzy_tags: list[str] = []
    for bucket, keys in keyword_map.items():
        if any(k in level_lower for k in keys):
            fuzzy_tags.extend(keys)
    for i, ex in enumerate(pool):
        if len(selected) >= max_count:
            break
        if i in seen:
            continue
        if any(k in ex.persona_tag for k in fuzzy_tags):
            selected.append(ex)
            seen.add(i)

    for i, ex in enumerate(pool):
        if len(selected) >= max_count:
            break
        if i in seen:
            continue
        selected.append(ex)
        seen.add(i)

    return selected[:max_count]


def select_chat_examples(
    examples: QAExampleSet | None,
    *,
    persona_level: str = "",
    persona_tag_hint: str = "",
    max_count: int = 1,
) -> list[QAChatExample]:
    """从 chat_examples 里挑选最贴当前 persona 的对话范例。

    选择策略与 ``select_ask_examples`` 一致；为节省 token，默认只取 1 条。
    """
    if examples is None:
        return []
    pool = list(examples.chat_examples)
    if not pool:
        return []

    selected: list[QAChatExample] = []
    seen: set[int] = set()

    if persona_tag_hint:
        for i, ex in enumerate(pool):
            if ex.persona_tag == persona_tag_hint:
                selected.append(ex)
                seen.add(i)
                break

    level_lower = persona_level.lower()
    keyword_map = {
        "weak": ["薄弱", "weak", "lost", "giveup"],
        "strong": ["优秀", "优等", "xueba", "top", "thinker", "striver", "mature"],
        "distracted": ["distracted", "restless", "offtopic", "off_topic", "走神"],
    }
    fuzzy_tags: list[str] = []
    for keys in keyword_map.values():
        if any(k in level_lower for k in keys):
            fuzzy_tags.extend(keys)
    for i, ex in enumerate(pool):
        if len(selected) >= max_count:
            break
        if i in seen:
            continue
        if any(k in ex.persona_tag for k in fuzzy_tags):
            selected.append(ex)
            seen.add(i)

    for i, ex in enumerate(pool):
        if len(selected) >= max_count:
            break
        if i in seen:
            continue
        selected.append(ex)
        seen.add(i)

    return selected[:max_count]
