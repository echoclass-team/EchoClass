"""StageProfile 加载与字段校验测试。

旧的 ``StudentAgent`` 集成测试（测 stage 注入到 prompt）随产品转型废弃；
新方向的 stage 注入由 ``test_student_questions.py`` / ``test_student_dialog.py``
间接覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemas.stage import StageProfile, load_stage_profile_by_id, load_stage_profiles

STAGE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "stage_profiles"

EXPECTED_STAGE_IDS = {
    "p_lower",
    "p_middle",
    "p_upper",
    "j_lower",
    "j_upper",
    "h",
}


# ============================================================ Loader


@pytest.fixture
def stages() -> list[StageProfile]:
    return load_stage_profiles(STAGE_DIR)


def test_load_all_stage_profiles(stages: list[StageProfile]) -> None:
    """应加载 6 个学段特征。"""
    assert len(stages) == 6
    ids = {s.id for s in stages}
    assert ids == EXPECTED_STAGE_IDS


def test_stage_profile_required_fields(stages: list[StageProfile]) -> None:
    """每个学段应包含关键字段且非空。"""
    for s in stages:
        assert s.id in EXPECTED_STAGE_IDS
        assert s.name
        assert s.grade_range
        assert s.age_range
        assert s.piaget_stage
        assert s.thinking_style
        assert s.language_style
        assert s.attention_features
        assert s.erikson_stage
        assert s.self_awareness
        assert s.peer_relationship
        # 列表字段至少各有 1 条
        assert len(s.cognitive_features) >= 1
        assert len(s.emotional_features) >= 1
        assert len(s.common_misconception_patterns) >= 1
        assert len(s.teaching_implications) >= 1
        assert len(s.sources) >= 1


def test_load_stage_by_id() -> None:
    """按 id 查询应返回正确学段。"""
    stage = load_stage_profile_by_id("p_middle", STAGE_DIR)
    assert stage is not None
    assert stage.id == "p_middle"
    assert "具体运算" in stage.piaget_stage


def test_load_stage_by_id_not_found() -> None:
    """不存在的 id 返回 None。"""
    assert load_stage_profile_by_id("nonexistent", STAGE_DIR) is None


def test_stage_json_matches_schema() -> None:
    """直接从 JSON 加载应不报错，且字段齐全。"""
    for fp in STAGE_DIR.glob("*.json"):
        if fp.name.startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        # 构造 StageProfile 不应抛异常
        StageProfile(**data)
