"""data/qa_examples/*.json 的加载与挑选逻辑测试。

不调用 LLM，直接验证：
- 6 个学段 JSON 都能加载且 schema 合法
- ``select_ask_examples`` / ``select_chat_examples`` 的优先级与降级
- 缺失文件返回 None 不抛异常
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag.qa_examples import (
    QAExampleSet,
    load_qa_examples,
    select_ask_examples,
    select_chat_examples,
)

QA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "qa_examples"

EXPECTED_STAGES = {"p_lower", "p_middle", "p_upper", "j_lower", "j_upper", "h"}


@pytest.mark.parametrize("stage_id", sorted(EXPECTED_STAGES))
def test_load_each_stage_json(stage_id: str) -> None:
    """6 个学段范例 JSON 都能加载且字段齐全。"""
    examples = load_qa_examples(stage_id, QA_DIR)
    assert isinstance(examples, QAExampleSet), f"{stage_id} 加载失败"
    assert examples.stage_id == stage_id
    assert examples.stage_name
    assert len(examples.ask_examples) >= 2, f"{stage_id} ask 范例少于 2 条"
    assert len(examples.chat_examples) >= 2, f"{stage_id} chat 范例少于 2 条"
    # 每个 ask_example 至少 1 个 question
    for ex in examples.ask_examples:
        assert ex.persona_tag
        assert ex.questions
        for q in ex.questions:
            assert q.content
            assert q.category in {
                "clarify_concept",
                "challenge_example",
                "extend_topic",
                "off_topic",
                "stuck_misconception",
            }
            assert q.difficulty in {"easy", "medium", "hard"}
    # 每个 chat_example 至少 2 turn
    for ex in examples.chat_examples:
        assert ex.persona_tag
        assert len(ex.turns) >= 2


def test_load_missing_stage_returns_none() -> None:
    examples = load_qa_examples("not_a_real_stage", QA_DIR)
    assert examples is None


def test_select_ask_examples_returns_empty_when_none() -> None:
    assert select_ask_examples(None, persona_level="weak") == []


def test_select_ask_examples_respects_max_count() -> None:
    examples = load_qa_examples("p_middle", QA_DIR)
    assert examples is not None
    selected = select_ask_examples(examples, persona_level="", max_count=1)
    assert len(selected) == 1


def test_select_ask_examples_persona_tag_hint_takes_priority() -> None:
    """显式 persona_tag_hint 命中时，无论 level 如何都先取该范例。"""
    examples = load_qa_examples("p_middle", QA_DIR)
    assert examples is not None
    available_tags = [ex.persona_tag for ex in examples.ask_examples]
    target = available_tags[-1]  # 取最后一个，确保不是默认排序首位

    selected = select_ask_examples(
        examples, persona_level="optional", persona_tag_hint=target, max_count=1
    )
    assert len(selected) == 1
    assert selected[0].persona_tag == target


def test_select_ask_examples_fuzzy_matches_weak_level() -> None:
    """persona_level 含'薄弱'/'weak' 时优先匹配 weak / lost / giveup 类范例。"""
    examples = load_qa_examples("p_middle", QA_DIR)
    assert examples is not None
    selected = select_ask_examples(
        examples, persona_level="基础薄弱", max_count=2
    )
    assert len(selected) == 2
    # 至少有一条 persona_tag 命中 weak 关键字（p_middle 范例集明确含 weak 类）
    assert any("weak" in ex.persona_tag for ex in selected)


def test_select_chat_examples_default_max_count_one() -> None:
    examples = load_qa_examples("h", QA_DIR)
    assert examples is not None
    selected = select_chat_examples(examples, persona_level="lost")
    assert len(selected) == 1


def test_select_chat_examples_falls_back_to_first_when_no_match() -> None:
    """level / hint 都匹配不上时，退化为按文件顺序取第一个。"""
    examples = load_qa_examples("p_lower", QA_DIR)
    assert examples is not None
    selected = select_chat_examples(
        examples, persona_level="完全无关词汇", persona_tag_hint="ghost", max_count=1
    )
    assert len(selected) == 1
    assert selected[0].persona_tag == examples.chat_examples[0].persona_tag


def test_qa_examples_json_files_match_expected_stages() -> None:
    """data/qa_examples/ 下应正好有 6 个学段文件 + 1 个 schema。"""
    files = {p.stem for p in QA_DIR.glob("*.json") if not p.stem.startswith("_")}
    assert files == EXPECTED_STAGES


def test_each_qa_examples_json_is_valid_json() -> None:
    """所有 qa_examples JSON 文件本身可以 parse。"""
    for fp in QA_DIR.glob("*.json"):
        with open(fp, encoding="utf-8") as f:
            json.load(f)  # 不抛异常即通过
