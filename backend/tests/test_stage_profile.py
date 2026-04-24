"""Tests for StageProfile loading and StudentAgent stage injection."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.stage import StageProfile, load_stage_profile_by_id, load_stage_profiles
from schemas.student import ClassroomContext, Persona

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


# ============================================================ Agent Integration


def _make_mock_llm(reply_json: str) -> LLMClient:
    mock_message = MagicMock()
    mock_message.content = reply_json
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    mock_client = MagicMock(spec=LLMClient)
    mock_client.chat = AsyncMock(return_value=mock_resp)
    return mock_client


_PERSONA = Persona(
    name="测试学生",
    personality="活泼好动",
    knowledge_level="中等",
    behavior_traits="积极举手",
    stage_id="p_middle",
)
_CONTEXT = ClassroomContext(subject="数学", topic="分数", history=[])
_REPLY = json.dumps(
    {
        "speaker_id": "测试学生",
        "intent": "answer_question",
        "content": "我觉得 1/2 就是一半！",
        "emotion": "自信",
    },
    ensure_ascii=False,
)


async def test_agent_without_stage() -> None:
    """不传 stage 时 agent 仍可工作（向后兼容）。"""
    mock_llm = _make_mock_llm(_REPLY)
    agent = StudentAgent(
        llm=mock_llm,
        persona=_PERSONA,
        context=_CONTEXT.model_copy(deep=True),
    )
    reply = await agent.respond("什么是分数？")
    assert reply.content

    # prompt 中不应包含学段共性段落标题
    call_args = mock_llm.chat.call_args
    system_msg = call_args[0][0][0]["content"]
    assert "学段共性特征" not in system_msg


async def test_agent_with_stage_injects_common_features() -> None:
    """传入 stage 后，prompt 应包含学段共性特征。"""
    stage = load_stage_profile_by_id("p_middle", STAGE_DIR)
    assert stage is not None

    mock_llm = _make_mock_llm(_REPLY)
    agent = StudentAgent(
        llm=mock_llm,
        persona=_PERSONA,
        context=_CONTEXT.model_copy(deep=True),
        stage=stage,
    )
    await agent.respond("什么是分数？")

    call_args = mock_llm.chat.call_args
    system_msg = call_args[0][0][0]["content"]
    # 应包含学段标题和关键特征
    assert "学段共性特征" in system_msg
    assert stage.name in system_msg
    assert stage.grade_range in system_msg
    assert stage.piaget_stage in system_msg
    # 至少有一个认知特征被注入
    assert stage.cognitive_features[0] in system_msg
    # 关键约束提示应出现
    assert "认知能力" in system_msg


async def test_agent_stage_does_not_break_existing_persona_injection() -> None:
    """传入 stage 不影响个体 persona 信息的注入。"""
    stage = load_stage_profile_by_id("p_lower", STAGE_DIR)
    mock_llm = _make_mock_llm(_REPLY)
    agent = StudentAgent(
        llm=mock_llm,
        persona=_PERSONA,
        context=_CONTEXT.model_copy(deep=True),
        stage=stage,
    )
    await agent.respond("什么是分数？")

    call_args = mock_llm.chat.call_args
    system_msg = call_args[0][0][0]["content"]
    # persona 个体信息仍在
    assert _PERSONA.name in system_msg
    assert _PERSONA.personality in system_msg
