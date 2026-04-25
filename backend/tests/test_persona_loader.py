"""Tests for persona loading from data/personas/ JSON files."""

from __future__ import annotations

from pathlib import Path

import pytest

from schemas.student import Persona, load_personas

PERSONAS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "personas"


@pytest.fixture
def personas() -> list[Persona]:
    return load_personas(PERSONAS_DIR)


VALID_STAGE_IDS = {"p_lower", "p_middle", "p_upper", "j_lower", "j_upper", "h"}


def test_load_all_personas(personas: list[Persona]) -> None:
    """应加载 18 个人设（6 学段 × 3 水平，跳过 _schema.json）。"""
    assert len(personas) == 18


def test_personas_cover_all_stages(personas: list[Persona]) -> None:
    """6 个学段每个都至少有 3 个人设。"""
    from collections import Counter

    stage_counts = Counter(p.stage_id for p in personas)
    assert set(stage_counts.keys()) == VALID_STAGE_IDS
    for stage_id, count in stage_counts.items():
        assert count >= 3, f"stage {stage_id} has only {count} personas"


def test_persona_required_fields(personas: list[Persona]) -> None:
    """每个人设必须有核心字段。"""
    for p in personas:
        assert p.name
        assert p.personality
        assert p.effective_level in {"优秀", "中等", "薄弱"}
        assert isinstance(p.behavior_traits, (str, list))
        assert p.behavior_traits_text  # 非空


def test_persona_rich_fields(personas: list[Persona]) -> None:
    """完整模式人设应有丰富字段。"""
    for p in personas:
        assert p.id
        assert p.gender in {"男", "女"}
        assert p.grade
        assert 6 <= p.age <= 18
        assert p.stage_id in VALID_STAGE_IDS
        assert p.speech_style
        assert len(p.catchphrases) >= 3
        assert len(p.misconception_tendencies) >= 1
        assert p.attention_span in {"short", "medium", "long"}
        assert p.summary


def test_backward_compatible_simple_persona() -> None:
    """简易模式（4 字段）仍然可用。"""
    p = Persona(
        name="测试",
        personality="活泼",
        knowledge_level="中等水平",
        behavior_traits="积极举手",
    )
    assert p.name == "测试"
    assert p.effective_level == "中等水平"
    assert p.behavior_traits_text == "积极举手"


def test_subject_level_takes_precedence() -> None:
    """subject_level 优先于 knowledge_level。"""
    p = Persona(
        name="测试",
        personality="活泼",
        knowledge_level="旧值",
        behavior_traits="积极",
        subject_level="优秀",
    )
    assert p.effective_level == "优秀"
