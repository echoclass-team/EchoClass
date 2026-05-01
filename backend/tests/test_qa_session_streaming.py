"""``QASession.stream_teacher_message`` 流式版本单元测试 (#71)。

覆盖：
- 流式事件序列与同步版语义一致（最终落库 + self_resolved 透传）
- 多轮流式仍能正确累积 dialog.messages
- pending 状态下自动 start_dialog
- 已 resolved / abandoned 的 dialog 调用流式接口抛 QASessionError
- text 空抛错
"""

from __future__ import annotations

from typing import Any

import pytest

from schemas.dialog import DialogMessage, DialogReplyResult, StudentStreamEvent
from schemas.followup import FollowupDecision
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession, QASessionError


class _FakePersona:
    def __init__(self, name: str) -> None:
        self.name = name


class _StreamingFakeAgent:
    """提供 generate_questions + stream_in_dialog 的鸭子类型 fake。"""

    def __init__(
        self,
        *,
        student_id: str,
        name: str,
        questions: list[dict[str, Any]],
        scripted_streams: list[list[StudentStreamEvent]] | None = None,
        followups: list[FollowupDecision] | None = None,
    ) -> None:
        self.persona = _FakePersona(name)
        self._student_id = student_id
        self._questions_template = questions
        self._streams = list(scripted_streams or [])
        self._followups = list(followups or [])
        self.stream_questions: list[str] = []

    async def generate_questions(self, lesson_meta: LessonMeta, *, count: int = 3):
        out: list[StudentQuestion] = []
        for i, q in enumerate(self._questions_template[:count]):
            out.append(
                StudentQuestion(
                    id=f"{self._student_id}-q{i}",
                    speaker_id=self._student_id,
                    speaker_name=self.persona.name,
                    content=q.get("content", f"问题{i}"),
                    category=q.get("category", "clarify_concept"),
                    difficulty=q.get("difficulty", "easy"),
                    linked_key_point=q.get("linked_key_point"),
                    rationale=q.get("rationale", ""),
                )
            )
        return out

    async def stream_in_dialog(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history: list[DialogMessage] | None = None,
    ):
        self.stream_questions.append(question.content)
        if not self._streams:
            yield StudentStreamEvent(type="delta", delta="嗯")
            yield StudentStreamEvent(
                type="final",
                result=DialogReplyResult(content="嗯", self_resolved=False, raw="嗯"),
            )
            return
        events = self._streams.pop(0)
        for evt in events:
            yield evt

    async def decide_followup(
        self,
        *,
        current_question: StudentQuestion,
        dialog_history: list[DialogMessage],
        lesson_meta: LessonMeta,
        asked_questions: list[StudentQuestion] | None = None,
    ) -> FollowupDecision:
        if not self._followups:
            return FollowupDecision.no_followup(reason="test default")
        return self._followups.pop(0)


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数",
        objectives=[],
        key_points=["理解几分之一"],
        difficult_points=[],
    )


def _followup_question() -> StudentQuestion:
    return StudentQuestion(
        id="S-f1",
        speaker_id="S",
        speaker_name="小明",
        content="那分子是什么意思？",
        category="clarify_concept",
        difficulty="easy",
        linked_key_point="理解几分之一",
        rationale="学生对分子产生了好奇。",
    )


# ============================================================ tests


async def test_stream_teacher_message_yields_delta_then_final() -> None:
    final_result = DialogReplyResult(
        content="哦！我懂了。", self_resolved=True, raw="哦！我懂了。[懂了]"
    )
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
        scripted_streams=[
            [
                StudentStreamEvent(type="delta", delta="哦！"),
                StudentStreamEvent(type="delta", delta="我懂了。"),
                StudentStreamEvent(type="final", result=final_result),
            ]
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None
    session.start_dialog(pending.id)

    events: list[StudentStreamEvent] = []
    async for evt in session.stream_teacher_message(pending.id, "你说说看？"):
        events.append(evt)

    assert [e.type for e in events] == ["delta", "delta", "final"]
    assert events[-1].result is not None
    assert events[-1].result.self_resolved is True

    # 历史落库：teacher + student 各 1 条
    dialog = session.get_dialog(pending.id)
    assert len(dialog.messages) == 2
    assert dialog.messages[0].role == "teacher"
    assert dialog.messages[0].content == "你说说看？"
    assert dialog.messages[1].role == "student"
    assert dialog.messages[1].content == "哦！我懂了。"


async def test_stream_teacher_message_auto_starts_pending_dialog() -> None:
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None
    assert pending.status == "pending"

    events = [evt async for evt in session.stream_teacher_message(pending.id, "你好")]
    assert events[-1].type == "final"
    assert session.get_dialog(pending.id).status == "active"


async def test_stream_teacher_message_rejects_resolved_dialog() -> None:
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None
    session.start_dialog(pending.id)
    session.mark_resolved(pending.id)

    with pytest.raises(QASessionError):
        async for _ in session.stream_teacher_message(pending.id, "再聊一句？"):
            pass


async def test_stream_teacher_message_rejects_empty_text() -> None:
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    with pytest.raises(QASessionError):
        async for _ in session.stream_teacher_message(pending.id, "   "):
            pass


async def test_stream_teacher_message_multi_turn_accumulates_history() -> None:
    """连续两轮 stream，dialog.messages 应有 4 条（2 teacher + 2 student）。"""
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
        scripted_streams=[
            [
                StudentStreamEvent(type="delta", delta="第一轮"),
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(
                        content="第一轮", self_resolved=False, raw="第一轮"
                    ),
                ),
            ],
            [
                StudentStreamEvent(type="delta", delta="第二轮"),
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(
                        content="第二轮", self_resolved=False, raw="第二轮"
                    ),
                ),
            ],
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    async for _ in session.stream_teacher_message(pending.id, "T1"):
        pass
    async for _ in session.stream_teacher_message(pending.id, "T2"):
        pass

    msgs = session.get_dialog(pending.id).messages
    assert [m.role for m in msgs] == ["teacher", "student", "teacher", "student"]
    assert [m.content for m in msgs] == ["T1", "第一轮", "T2", "第二轮"]


async def test_stream_teacher_message_yields_followup_after_final() -> None:
    followup = _followup_question()
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
        scripted_streams=[
            [
                StudentStreamEvent(type="delta", delta="懂一点了"),
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(
                        content="懂一点了", self_resolved=False, raw="懂一点了"
                    ),
                ),
            ],
        ],
        followups=[
            FollowupDecision(
                should_followup=True,
                new_question=followup,
                reason="学生还有追问",
            )
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    events = [evt async for evt in session.stream_teacher_message(pending.id, "T1")]

    assert [e.type for e in events] == ["delta", "final", "followup"]
    assert events[-1].new_question == followup
    dialog = session.get_dialog(pending.id)
    assert [q.content for q in dialog.asked_questions] == ["Q1", "那分子是什么意思？"]
    assert [m.role for m in dialog.messages] == ["teacher", "student", "student"]
    assert dialog.messages[-1].is_new_question is True
    assert dialog.messages[-1].question_id == followup.id


async def test_stream_teacher_message_uses_latest_followup_as_current_question() -> (
    None
):
    followup = _followup_question()
    a = _StreamingFakeAgent(
        student_id="S",
        name="小明",
        questions=[{"content": "Q1"}],
        scripted_streams=[
            [
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(content="第一轮", self_resolved=False),
                ),
            ],
            [
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(content="第二轮", self_resolved=False),
                ),
            ],
        ],
        followups=[
            FollowupDecision(
                should_followup=True,
                new_question=followup,
                reason="学生还有追问",
            ),
            FollowupDecision.no_followup(reason="停止追问"),
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    async for _ in session.stream_teacher_message(pending.id, "T1"):
        pass
    async for _ in session.stream_teacher_message(pending.id, "T2"):
        pass

    assert a.stream_questions == ["Q1", "那分子是什么意思？"]
