"""``agents.feedback`` 单元测试 (#M3-A2 / #138)。

仅覆盖骨架 + mock 行为，不调真实 LLM。
真实 LLM 路径（``llm`` 非空）仅断言抛 ``NotImplementedError``，等 #M3-A4 替换。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.feedback import FeedbackAgent
from schemas.evaluation import EvaluationReport, RubricScore
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta
from services.qa_session import QASession


# ============================================================ helpers


def _fake_session(session_id: str = "sess-test") -> QASession:
    lesson = LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=["理解分数含义"],
        key_points=["分数的定义"],
        difficult_points=["平均分的理解"],
    )
    return QASession(lesson_meta=lesson, session_id=session_id)


def _fake_evaluation(session_id: str = "sess-test") -> EvaluationReport:
    return EvaluationReport(
        session_id=session_id,
        rubric_version="v0",
        scores=[
            RubricScore(
                dimension="MR",
                score=3,
                rationale="测试用 rationale",
                evidence=[],
            )
        ],
        overall=3.0,
        generated_at=datetime.now().astimezone(),
    )


# ============================================================ mock generate


async def test_mock_generate_returns_teacher_feedback() -> None:
    fb = await FeedbackAgent().generate(_fake_session())
    assert isinstance(fb, TeacherFeedback)


async def test_mock_generate_lists_are_nonempty() -> None:
    """契约：strengths / improvements / next_steps 列表不为空。"""
    fb = await FeedbackAgent().generate(_fake_session())
    assert len(fb.strengths) >= 1
    assert len(fb.improvements) >= 1
    assert len(fb.next_steps) >= 1


async def test_mock_generate_uses_placeholder_marker() -> None:
    """mock 文案带 ``[mock]`` 前缀，避免被误当真实反馈。"""
    fb = await FeedbackAgent().generate(_fake_session())
    all_lines = fb.strengths + fb.improvements + fb.next_steps
    assert all("[mock]" in line for line in all_lines)


async def test_mock_generate_tone_is_valid_enum() -> None:
    fb = await FeedbackAgent().generate(_fake_session())
    assert fb.tone in {"encouraging", "neutral", "critical"}


async def test_mock_generate_accepts_optional_evaluation() -> None:
    """``evaluation`` 是可选参数；传 / 不传都应成功。"""
    agent = FeedbackAgent()
    session = _fake_session()
    # 不传
    fb1 = await agent.generate(session)
    # 传
    fb2 = await agent.generate(session, _fake_evaluation(session.id))
    assert isinstance(fb1, TeacherFeedback)
    assert isinstance(fb2, TeacherFeedback)


async def test_mock_generated_at_is_recent() -> None:
    before = datetime.now().astimezone()
    fb = await FeedbackAgent().generate(_fake_session())
    after = datetime.now().astimezone()
    assert before <= fb.generated_at.astimezone() <= after


async def test_mock_feedback_is_json_serializable_for_b3() -> None:
    """B3 / B4 通过 ``model_dump_json`` 消费反馈；保证可序列化往返。"""
    fb = await FeedbackAgent().generate(_fake_session())
    payload = fb.model_dump_json()
    restored = TeacherFeedback.model_validate_json(payload)
    assert restored.tone == fb.tone
    assert restored.strengths == fb.strengths


# ============================================================ real path stub


async def test_real_generate_not_implemented_yet() -> None:
    """传入 LLMClient 的真实路径应在 #M3-A4 实现前明确抛错。"""
    fake_llm = MagicMock()
    agent = FeedbackAgent(llm=fake_llm)
    with pytest.raises(NotImplementedError, match="#M3-A4"):
        await agent.generate(_fake_session())


# ============================================================ prompt file


def test_feedback_prompt_template_exists() -> None:
    prompt_path = (
        Path(__file__).resolve().parent.parent / "prompts" / "feedback.j2"
    )
    assert prompt_path.exists()
    assert prompt_path.stat().st_size > 0
