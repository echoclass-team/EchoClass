"""FeedbackAgent 真实 LLM 冒烟测试 (#M3-A4 验收)。

默认 skip；设 ``PYTEST_LIVE=1`` 且配置了 ``OPENAI_API_KEY`` 时才执行。
本测试会真实调用 LLM，消耗 token；仅在手动验收或 release 前跑。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from agents.feedback import FeedbackAgent
from llm.client import LLMClient
from schemas.dialog import DialogMessage, DialogSession, QuestionProgress
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession


pytestmark = pytest.mark.skipif(
    os.getenv("PYTEST_LIVE") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="set PYTEST_LIVE=1 and OPENAI_API_KEY to run live LLM tests",
)


def _seed_session() -> QASession:
    lesson = LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=["理解分数含义"],
        key_points=["分数的定义", "平均分的概念"],
        difficult_points=["平均分的理解"],
    )
    session = QASession(lesson_meta=lesson, session_id="sess-live-fb")
    question = StudentQuestion(
        id="s1-q1",
        speaker_id="s1",
        speaker_name="小明",
        content="老师，1/2 和 1/3 哪个大呀？",
        category="clarify_concept",
        difficulty="easy",
        rationale="容易被数字大小误导。",
    )
    now = datetime.now(timezone.utc)
    dialog = DialogSession(
        id="s1",
        student_id="s1",
        question=question,
        status="resolved",
        messages=[
            DialogMessage(
                role="student",
                content="老师，1/2 和 1/3 哪个大呀？",
                timestamp=now,
                is_new_question=True,
                question_id="s1-q1",
            ),
            DialogMessage(
                role="teacher",
                content="我们先想一想：把一块饼平均分成 2 份和分成 3 份，哪一份更大？",
                timestamp=now,
            ),
            DialogMessage(
                role="student",
                content="分成 2 份的一份大！所以 1/2 大。",
                timestamp=now,
                self_resolved=True,
            ),
        ],
        asked_questions=[question],
        question_progress=[
            QuestionProgress(
                question_id="s1-q1",
                status="resolved",
                turns_used=1,
                message_start_idx=0,
                message_end_idx=3,
                resolution_source="self_resolve",
            )
        ],
        current_question_idx=0,
        resolution_source="self_resolve",
    )
    session.dialogs[dialog.id] = dialog
    return session


async def test_feedback_live_smoke() -> None:
    agent = FeedbackAgent(llm=LLMClient())
    session = _seed_session()

    fb = await agent.generate(session)

    assert isinstance(fb, TeacherFeedback)
    assert fb.tone in {"encouraging", "neutral", "critical"}
    assert len(fb.strengths) >= 1
    assert len(fb.improvements) >= 1
    assert len(fb.next_steps) >= 1
