"""DirectorAgent 单元测试。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from legacy.agents.director import DirectorAgent
from legacy.schemas.director import DirectorConfig, Message
from llm.client import LLMClient
from schemas.stage import StageProfile, load_stage_profile_by_id
from schemas.student import Persona, load_personas


def stage(stage_id: str) -> StageProfile:
    return StageProfile(
        id=stage_id,
        name=stage_id,
        grade_range="",
        age_range="",
        piaget_stage="",
        cognitive_features=[],
        thinking_style="",
        language_style="",
        typical_expressions=[],
        attention_features="低年级注意力短" if stage_id == "p_lower" else "注意力稳定",
        memory_features="",
        erikson_stage="",
        emotional_features=["好动", "易走神"] if stage_id == "p_lower" else ["克制"],
        self_awareness="",
        peer_relationship="",
        motivation_patterns=[],
        classroom_behaviors=[],
        common_misconception_patterns=[],
        teaching_implications=[],
        sources=[],
    )


STUDENTS = [
    Persona(
        id="s1",
        name="小红",
        personality="内向",
        knowledge_level="中等",
        behavior_traits="安静",
        interaction_frequency="low",
        attention_span="short",
    ),
    Persona(
        id="s2",
        name="小明",
        personality="活泼",
        knowledge_level="中等",
        behavior_traits="积极",
        interaction_frequency="high",
        attention_span="short",
    ),
    Persona(
        id="s3",
        name="小华",
        personality="认真",
        knowledge_level="优秀",
        behavior_traits="举手",
        interaction_frequency="medium",
        attention_span="long",
    ),
]


def mock_llm(payload: Any) -> LLMClient:
    content = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    )
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_twenty_turns_distribution_not_cluster_or_dead_air() -> None:
    llm = mock_llm("not json")
    agent = DirectorAgent(
        llm=llm, config=DirectorConfig(seed=1, speaker_cooldown_seconds=5)
    )
    history: list[Message] = []
    speaks: dict[str, int] = {student.id: 0 for student in STUDENTS}
    dead_air = 0
    last_active: dict[str, int] = {}
    for i in range(20):
        elapsed = i * 10
        d = await agent.decide(
            "谁想试试？", stage("p_middle"), STUDENTS, history, elapsed
        )
        assert d.actions
        if any(a.action_type in {"raise_hand", "speak", "daydream"} for a in d.actions):
            dead_air = 0
        else:
            dead_air += 1
        assert dead_air <= 2
        for a in d.actions:
            if a.action_type in {"raise_hand", "speak"}:
                if a.speaker_id in last_active:
                    assert elapsed - last_active[a.speaker_id] >= 5
                last_active[a.speaker_id] = elapsed
                speaks[a.speaker_id] = speaks.get(a.speaker_id, 0) + 1
                history.append(
                    Message(
                        role="student",
                        speaker_id=a.speaker_id,
                        content="发言",
                        timestamp_seconds=elapsed,
                    )
                )
    assert max(speaks.values()) - min(speaks.values()) <= 4
    assert all(count > 0 for count in speaks.values())


@pytest.mark.asyncio
async def test_p_lower_delay_shorter_and_more_daydream_than_high_school() -> None:
    llm = mock_llm("invalid")
    lower = DirectorAgent(llm=llm, config=DirectorConfig(seed=2))
    high = DirectorAgent(llm=llm, config=DirectorConfig(seed=2))
    lower_ds, high_ds, lower_dream, high_dream = [], [], 0, 0
    lower_history: list[Message] = []
    high_history: list[Message] = []
    for i in range(8):
        elapsed = i * 30
        ld = await lower.decide(
            "继续听讲。", stage("p_lower"), STUDENTS, lower_history, elapsed
        )
        hd = await high.decide(
            "继续听讲。", stage("h"), STUDENTS, high_history, elapsed
        )
        lower_ds.append(ld.next_action_delay_ms)
        high_ds.append(hd.next_action_delay_ms)
        lower_dream += sum(a.action_type == "daydream" for a in ld.actions)
        high_dream += sum(a.action_type == "daydream" for a in hd.actions)
        for action in ld.actions:
            lower_history.append(
                Message(
                    role="student",
                    speaker_id=action.speaker_id,
                    content="动作",
                    timestamp_seconds=elapsed,
                )
            )
        for action in hd.actions:
            high_history.append(
                Message(
                    role="student",
                    speaker_id=action.speaker_id,
                    content="动作",
                    timestamp_seconds=elapsed,
                )
            )
    assert sum(lower_ds) / len(lower_ds) < sum(high_ds) / len(high_ds)
    assert lower_dream > high_dream


@pytest.mark.asyncio
async def test_called_student_must_speak_priority_5() -> None:
    agent = DirectorAgent(
        llm=mock_llm(
            {
                "actions": [
                    {"speaker_id": "s1", "action_type": "silent", "priority": 1}
                ],
                "next_action_delay_ms": 999,
                "rationale": "x",
            }
        )
    )
    d = await agent.decide("小红，你来回答。", stage("p_middle"), STUDENTS, [], 10)
    assert d.actions[0].speaker_id == "s1"
    assert d.actions[0].action_type == "speak"
    assert d.actions[0].priority == 5


@pytest.mark.asyncio
async def test_llm_code_block_can_parse() -> None:
    raw = '```json\n{"actions":[{"speaker_id":"s2","action_type":"raise_hand","priority":4}],"next_action_delay_ms":1234,"rationale":"想举手"}\n```'
    d = await DirectorAgent(llm=mock_llm(raw)).decide(
        "谁会？", stage("p_middle"), STUDENTS, [], 1
    )
    assert d.actions[0].speaker_id == "s2"
    assert 800 <= d.next_action_delay_ms <= 6000
    assert d.rationale == "想举手"


@pytest.mark.asyncio
async def test_llm_name_is_normalized_and_multiple_speaks_downgraded() -> None:
    payload = {
        "actions": [
            {"speaker_id": "小红", "action_type": "speak", "priority": 3},
            {"speaker_id": "小明", "action_type": "speak", "priority": 5},
        ],
        "next_action_delay_ms": 1000,
        "rationale": "姓名归一化",
    }
    d = await DirectorAgent(llm=mock_llm(payload)).decide(
        "谁会？", stage("p_middle"), STUDENTS, [], 10
    )
    assert {action.speaker_id for action in d.actions} == {"s1", "s2"}
    assert sum(action.action_type == "speak" for action in d.actions) == 1
    assert (
        next(action for action in d.actions if action.speaker_id == "s2").action_type
        == "speak"
    )


@pytest.mark.asyncio
async def test_invalid_json_fallback() -> None:
    d = await DirectorAgent(llm=mock_llm("oops"), config=DirectorConfig(seed=3)).decide(
        "谁会？", stage("p_middle"), STUDENTS, [], 1
    )
    assert d.actions
    assert "规则层" in d.rationale


@pytest.mark.asyncio
async def test_unknown_speaker_and_illegal_action_filtered_or_corrected() -> None:
    payload = {
        "actions": [
            {"speaker_id": "ghost", "action_type": "speak", "priority": 5},
            {"speaker_id": "s2", "action_type": "speak", "priority": 5},
        ],
        "next_action_delay_ms": 1000,
        "rationale": "过滤",
    }
    hist = [
        Message(role="student", speaker_id="s2", content="刚说过", timestamp_seconds=9)
    ]
    d = await DirectorAgent(
        llm=mock_llm(payload), config=DirectorConfig(speaker_cooldown_seconds=20)
    ).decide("谁会？", stage("p_middle"), STUDENTS, hist, 10)
    assert all(a.speaker_id != "ghost" for a in d.actions)
    assert all(a.speaker_id != "s2" for a in d.actions)
    assert d.actions[0].speaker_id in {"s1", "s3"}

    bad = {
        "actions": [{"speaker_id": "s2", "action_type": "jump", "priority": 5}],
        "next_action_delay_ms": 1000,
        "rationale": "bad",
    }
    d2 = await DirectorAgent(llm=mock_llm(bad), config=DirectorConfig(seed=4)).decide(
        "谁会？", stage("p_middle"), STUDENTS, [], 10
    )
    assert d2.actions[0].action_type in {"raise_hand", "speak", "daydream", "silent"}


def test_try_director_persona_filtering_has_same_stage() -> None:
    loaded_stage = load_stage_profile_by_id("p_lower")
    assert loaded_stage is not None
    students = [
        persona for persona in load_personas() if persona.stage_id == loaded_stage.id
    ][:5]
    assert len(students) >= 3
    assert all(persona.stage_id == loaded_stage.id for persona in students)


@pytest.mark.asyncio
async def test_stage_persona_mismatch_raises_value_error() -> None:
    students = [student.model_copy(update={"stage_id": "h"}) for student in STUDENTS]
    with pytest.raises(ValueError, match="stage.*persona|stage_id"):
        await DirectorAgent(llm=mock_llm("invalid")).decide(
            "谁会？", stage("p_middle"), students, [], 10
        )


@pytest.mark.asyncio
async def test_duplicate_speaker_id_raises_value_error() -> None:
    students = [
        STUDENTS[0],
        STUDENTS[1].model_copy(update={"id": "s1"}),
        STUDENTS[2],
    ]
    with pytest.raises(ValueError, match="speaker_id.*unique"):
        await DirectorAgent(llm=mock_llm("invalid")).decide(
            "谁会？", stage("p_middle"), students, [], 10
        )


@pytest.mark.asyncio
async def test_same_speaker_multiple_non_speak_actions_deduped_by_priority() -> None:
    payload = {
        "actions": [
            {"speaker_id": "s1", "action_type": "daydream", "priority": 5},
            {"speaker_id": "s1", "action_type": "raise_hand", "priority": 1},
        ],
        "next_action_delay_ms": 1000,
        "rationale": "去重",
    }
    d = await DirectorAgent(llm=mock_llm(payload)).decide(
        "谁会？", stage("p_middle"), STUDENTS, [], 10
    )
    assert len([action for action in d.actions if action.speaker_id == "s1"]) == 1
    assert d.actions[0].action_type == "raise_hand"


@pytest.mark.asyncio
async def test_raise_hand_ignores_speak_cooldown_but_speak_filtered() -> None:
    hist = [
        Message(role="student", speaker_id="s1", content="刚发言", timestamp_seconds=9)
    ]
    raise_hand_payload = {
        "actions": [{"speaker_id": "s1", "action_type": "raise_hand", "priority": 5}],
        "next_action_delay_ms": 1000,
        "rationale": "举手不受发言冷却影响",
    }
    d = await DirectorAgent(
        llm=mock_llm(raise_hand_payload),
        config=DirectorConfig(speaker_cooldown_seconds=20),
    ).decide("谁会？", stage("p_middle"), STUDENTS, hist, 10)
    assert any(
        action.speaker_id == "s1" and action.action_type == "raise_hand"
        for action in d.actions
    )

    speak_payload = {
        "actions": [{"speaker_id": "s1", "action_type": "speak", "priority": 5}],
        "next_action_delay_ms": 1000,
        "rationale": "发言受冷却影响",
    }
    d2 = await DirectorAgent(
        llm=mock_llm(speak_payload), config=DirectorConfig(speaker_cooldown_seconds=20)
    ).decide("谁会？", stage("p_middle"), STUDENTS, hist, 10)
    assert all(
        not (action.speaker_id == "s1" and action.action_type == "speak")
        for action in d2.actions
    )


def test_director_config_restricts_class_size_to_issue_range() -> None:
    with pytest.raises(ValidationError):
        DirectorConfig(min_students=1)
    with pytest.raises(ValidationError):
        DirectorConfig(max_students=9)
    with pytest.raises(ValidationError):
        DirectorConfig(min_students=5, max_students=4)
