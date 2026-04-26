from __future__ import annotations

from rag.misconceptions import load_misconceptions, match_misconceptions


def test_load_misconceptions_loads_math_primary_entries() -> None:
    items = load_misconceptions()

    assert any(item.id == "math_fraction_average_01" for item in items)
    assert any(item.subject == "数学" and "p_middle" in item.stage for item in items)


def test_match_misconceptions_matches_fraction_topic_by_overlap() -> None:
    matches = match_misconceptions(
        subject="数学",
        stage_id="p_middle",
        key_points=["几分之一的含义"],
        topic="分数",
    )

    assert matches
    assert any("fraction" in item.id for item in matches)
    assert matches[0].subject == "数学"


def test_match_misconceptions_requires_key_point_when_available() -> None:
    matches = match_misconceptions(
        subject="数学",
        stage_id="p_middle",
        key_points=["完全不相关的教学重点"],
        topic="分数",
    )

    assert matches == []


def test_match_misconceptions_supports_english_subject_aliases() -> None:
    # 数据已统一为中文 subject；这里用英文别名查询，验证别名归一化仍然有效。
    matches = match_misconceptions(
        subject="geography",
        stage_id="j_lower",
        key_points=["等高线地形图"],
        topic="地理",
    )

    assert any(item.subject == "地理" for item in matches)
