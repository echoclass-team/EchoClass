"""EvaluatorAgent 真实 LLM 冒烟测试。

默认 skip；设 ``PYTEST_LIVE=1`` 且配置了 ``OPENAI_API_KEY`` 时才执行。
本测试会真实调用 LLM，消耗 token；仅在手动验收或 release 前跑。

验证目标
--------
- prompt 渲染 + LLM 调用 + JSON 解析端到端不崩
- 返回 ``EvaluationReport``，``overall`` 要么为 0-4 浮点，要么为 ``"unavailable"`` 降级
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from agents.evaluator import EvaluatorAgent
from llm.client import LLMClient
from schemas.dialog import DialogMessage, DialogSession, QuestionProgress
from schemas.evaluation import EvaluationReport
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
    session = QASession(lesson_meta=lesson, session_id="sess-live-eval")
    question = StudentQuestion(
        id="s1-q1",
        speaker_id="s1",
        speaker_name="小明",
        content="老师，分数是不是就是分东西？",
        category="clarify_concept",
        difficulty="easy",
        rationale="学生对分数初印象只停留在'分'的动作。",
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
                content="老师，分数是不是就是分东西？",
                timestamp=now,
                is_new_question=True,
                question_id="s1-q1",
            ),
            DialogMessage(
                role="teacher",
                content="问得好！那你能说说分东西和我们今天讲的平均分有什么不一样吗？",
                timestamp=now,
            ),
            DialogMessage(
                role="student",
                content="哦——是不是要分得一样多才算？",
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


async def test_evaluator_live_smoke() -> None:
    evaluator = EvaluatorAgent(llm=LLMClient())
    session = _seed_session()

    report = await evaluator.evaluate(session)

    assert isinstance(report, EvaluationReport)
    assert report.session_id == session.id
    assert report.rubric_version == "v0"
    if report.overall != "unavailable":
        assert isinstance(report.overall, float)
        assert 0.0 <= report.overall <= 4.0
