"""``agents.feedback`` 单元测试 (#M3-A2 / #138)。

覆盖 mock 行为、真实路径 JSON 解析与失败降级；不调真实 LLM。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


# ============================================================ real generate


async def test_real_generate_parses_llm_json() -> None:
    fake_llm = MagicMock()
    fake_llm.chat = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "strengths": ["先肯定学生的提问。"],
                                "improvements": ["遇迷思时先问例子。"],
                                "next_steps": ["准备 2 个反例。"],
                                "tone": "encouraging",
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )
    )
    agent = FeedbackAgent(llm=fake_llm)

    fb = await agent.generate(_fake_session(), _fake_evaluation())

    assert fb.tone == "encouraging"
    assert fb.strengths == ["先肯定学生的提问。"]
    assert fb.improvements == ["遇迷思时先问例子。"]
    assert fb.next_steps == ["准备 2 个反例。"]
    fake_llm.chat.assert_awaited_once()
    messages = fake_llm.chat.await_args.args[0]
    assert messages[0]["role"] == "system"
    assert "教案" in messages[0]["content"]


async def test_real_generate_defaults_invalid_tone_to_neutral() -> None:
    fake_llm = MagicMock()
    fake_llm.chat = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "strengths": ["a"],
                                "improvements": ["b"],
                                "next_steps": ["c"],
                                "tone": "不合法枚举",
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )
    )
    agent = FeedbackAgent(llm=fake_llm)

    fb = await agent.generate(_fake_session())

    assert fb.tone == "neutral"


async def test_real_generate_short_circuits_on_unavailable_evaluation() -> None:
    """评估已降级（overall=unavailable）时，不应再调 LLM，直接 fallback。"""
    fake_llm = MagicMock()
    fake_llm.chat = AsyncMock()  # 不应被调用
    agent = FeedbackAgent(llm=fake_llm)
    unavailable_eval = EvaluationReport(
        session_id="sess-test",
        rubric_version="v0",
        scores=[],
        overall="unavailable",
        generated_at=datetime.now().astimezone(),
    )

    fb = await agent.generate(_fake_session(), unavailable_eval)

    fake_llm.chat.assert_not_awaited()
    assert fb.tone == "neutral"
    all_lines = fb.strengths + fb.improvements + fb.next_steps
    assert all("[fallback]" in line for line in all_lines)


async def test_real_generate_falls_back_when_llm_fails() -> None:
    fake_llm = MagicMock()
    fake_llm.chat = AsyncMock(side_effect=RuntimeError("boom"))
    agent = FeedbackAgent(llm=fake_llm)

    fb = await agent.generate(_fake_session())

    assert fb.tone == "neutral"
    assert len(fb.strengths) >= 1
    assert len(fb.improvements) >= 1
    assert len(fb.next_steps) >= 1
    all_lines = fb.strengths + fb.improvements + fb.next_steps
    assert all("[fallback]" in line for line in all_lines)


# ============================================================ prompt file


def test_feedback_prompt_template_exists() -> None:
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "feedback.j2"
    assert prompt_path.exists()
    assert prompt_path.stat().st_size > 0
