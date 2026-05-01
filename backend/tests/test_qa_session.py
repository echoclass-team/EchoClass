"""QASession orchestrator 集成测试（mock StudentAgent，不调真 LLM）。

覆盖：
- spawn 为每个学生创建一个 thread dialog，并按学生顺序入队
- next_pending FIFO 行为；start_dialog 后从 pending 队列移除
- send_teacher_message 自动 start_dialog；学生回复落历史；self_resolved 透传
- mark_resolved / abandon_dialog 状态流转 + 幂等
- summary 统计 covered_key_points / broken_misconception_ids / resolution_sources
- spawn 时单一学生失败不影响其他学生
"""

from __future__ import annotations

from typing import Any

import pytest

from schemas.dialog import DialogMessage, DialogReplyResult
from schemas.followup import FollowupDecision
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession, QASessionError


# ============================================================ Fakes


class FakePersona:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeStudentAgent:
    """只提供 QASession 依赖的最小鸭子类型接口。

    QASession 不依赖 StudentAgent 的其他行为，因此用一个鸭子类型的 fake 即可。
    """

    def __init__(
        self,
        *,
        student_id: str,
        name: str,
        questions: list[dict[str, Any]],
        replies: list[DialogReplyResult] | None = None,
        followups: list[FollowupDecision] | None = None,
        fail_on_generate: bool = False,
    ) -> None:
        self.persona = FakePersona(name)
        self._student_id = student_id
        self._questions_template = questions
        self._replies = list(replies or [])
        self._followups = list(followups or [])
        self._fail_on_generate = fail_on_generate
        self.respond_questions: list[str] = []
        self.decide_current_questions: list[str] = []

    async def generate_questions(self, lesson_meta: LessonMeta, *, count: int = 3):
        if self._fail_on_generate:
            raise RuntimeError(f"{self.persona.name} simulated LLM failure")
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
                    linked_misconception_id=q.get("linked_misconception_id"),
                    rationale=q.get("rationale", ""),
                )
            )
        return out

    async def respond_in_dialog(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history=None,
    ) -> DialogReplyResult:
        self.respond_questions.append(question.content)
        if not self._replies:
            return DialogReplyResult(content="嗯……", self_resolved=False, raw="嗯……")
        return self._replies.pop(0)

    async def decide_followup(
        self,
        *,
        current_question: StudentQuestion,
        dialog_history: list[DialogMessage],
        lesson_meta: LessonMeta,
        asked_questions: list[StudentQuestion] | None = None,
    ) -> FollowupDecision:
        self.decide_current_questions.append(current_question.content)
        if not self._followups:
            return FollowupDecision.no_followup(reason="test default")
        return self._followups.pop(0)


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数",
        objectives=[],
        key_points=["理解几分之一", "比较大小"],
        difficult_points=["平均分"],
    )


def _followup_question(
    qid: str = "A-f1", content: str = "那分子是什么意思？"
) -> StudentQuestion:
    return StudentQuestion(
        id=qid,
        speaker_id="A",
        speaker_name="学生A",
        content=content,
        category="clarify_concept",
        difficulty="easy",
        linked_key_point="比较大小",
        rationale="学生对分子产生了好奇。",
    )


# ============================================================ tests


async def test_spawn_creates_one_thread_per_student() -> None:
    """M3 下 spawn 应为每个学生创建一个 dialog，忽略后续候选问题。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[
            {"content": "A1"},
            {"content": "A2"},
        ],
    )
    b = FakeStudentAgent(
        student_id="B",
        name="学生B",
        questions=[
            {"content": "B1"},
            {"content": "B2"},
        ],
    )

    session = QASession(lesson_meta=_lesson())
    questions = await session.spawn([a, b], questions_per_student=2)

    assert [q.content for q in questions] == ["A1", "B1"]
    assert session.pending_count() == 2
    assert list(session.dialogs.keys()) == ["A", "B"]
    assert session.dialogs["A"].question.content == "A1"
    assert [q.content for q in session.dialogs["A"].asked_questions] == ["A1"]


async def test_next_pending_fifo_order_and_drains() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
    )
    b = FakeStudentAgent(
        student_id="B",
        name="学生B",
        questions=[{"content": "B1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a, b], questions_per_student=2)

    first = session.next_pending()
    assert first is not None and first.question.content == "A1"

    session.start_dialog(first.id)
    second = session.next_pending()
    assert second is not None and second.question.content == "B1"

    session.start_dialog(second.id)
    assert session.next_pending() is None


async def test_send_teacher_message_auto_starts_and_records_history() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
        replies=[
            DialogReplyResult(
                content="哦，明白了。", self_resolved=False, raw="哦，明白了。"
            )
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)

    pending = session.next_pending()
    assert pending is not None

    result = await session.send_teacher_message(pending.id, "几分之一就是分母。")

    assert result.content == "哦，明白了。"
    dialog = session.get_dialog(pending.id)
    assert dialog.status == "active"
    assert len(dialog.messages) == 2
    assert dialog.messages[0].role == "teacher"
    assert dialog.messages[1].role == "student"
    assert dialog.messages[1].content == "哦，明白了。"


async def test_send_teacher_message_records_followup_question() -> None:
    followup = _followup_question()
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
        replies=[DialogReplyResult(content="我懂一点了。", self_resolved=False)],
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

    result = await session.send_teacher_message(pending.id, "先看分母。")

    assert result.content == "我懂一点了。"
    dialog = session.get_dialog(pending.id)
    assert [q.content for q in dialog.asked_questions] == ["A1", "那分子是什么意思？"]
    assert [m.role for m in dialog.messages] == ["teacher", "student", "student"]
    followup_msg = dialog.messages[-1]
    assert followup_msg.content == "那分子是什么意思？"
    assert followup_msg.is_new_question is True
    assert followup_msg.question_id == followup.id


async def test_send_teacher_message_uses_latest_followup_as_current_question() -> None:
    followup = _followup_question()
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
        replies=[
            DialogReplyResult(content="第一轮回复", self_resolved=False),
            DialogReplyResult(content="第二轮回复", self_resolved=False),
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

    await session.send_teacher_message(pending.id, "T1")
    await session.send_teacher_message(pending.id, "T2")

    assert a.respond_questions == ["A1", "那分子是什么意思？"]
    assert a.decide_current_questions == ["A1", "那分子是什么意思？"]


async def test_send_teacher_message_propagates_self_resolved_flag() -> None:
    """学生 [懂了] 标记应被 result.self_resolved 透传给调用方，但不自动结会话。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
        replies=[
            DialogReplyResult(
                content="原来如此！",
                self_resolved=True,
                raw="原来如此！\n[懂了]",
            )
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    result = await session.send_teacher_message(pending.id, "...")
    assert result.self_resolved is True
    # 但 dialog 不会自动 resolved，等待师范生确认
    assert session.get_dialog(pending.id).status == "active"
    # issue #102: self_resolved 也要落到 dialog.messages，便于 GET 复原
    student_msg = session.get_dialog(pending.id).messages[-1]
    assert student_msg.role == "student"
    assert student_msg.self_resolved is True


async def test_mark_resolved_records_source_and_is_idempotent() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    session.start_dialog(pending.id)
    session.mark_resolved(pending.id, source="self_resolve")
    dialog = session.get_dialog(pending.id)
    assert dialog.status == "resolved"
    assert dialog.resolution_source == "self_resolve"
    assert dialog.ended_at is not None

    # 再次 mark_resolved 是幂等的
    session.mark_resolved(pending.id, source="teacher_marked")
    assert (
        session.get_dialog(pending.id).resolution_source == "self_resolve"
    )  # 不被覆盖


async def test_mark_resolved_after_abandoned_raises() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    session.abandon_dialog(pending.id)
    with pytest.raises(QASessionError):
        session.mark_resolved(pending.id, source="teacher_marked")


async def test_send_message_on_resolved_raises() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    session.start_dialog(pending.id)
    session.mark_resolved(pending.id, source="teacher_marked")

    with pytest.raises(QASessionError):
        await session.send_teacher_message(pending.id, "再问一句")


async def test_summary_aggregates_resolved_metadata() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[
            {
                "content": "A1",
                "category": "stuck_misconception",
                "linked_key_point": "理解几分之一",
                "linked_misconception_id": "m_001",
            }
        ],
    )
    b = FakeStudentAgent(
        student_id="B",
        name="学生B",
        questions=[
            {
                "content": "B1",
                "category": "clarify_concept",
                "linked_key_point": "比较大小",
            }
        ],
    )
    c = FakeStudentAgent(
        student_id="C",
        name="学生C",
        questions=[{"content": "C1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a, b, c], questions_per_student=3)

    ids = list(session.dialogs.keys())
    session.mark_resolved(ids[0], source="self_resolve")
    session.mark_resolved(ids[1], source="teacher_marked")
    session.abandon_dialog(ids[2])

    summary = session.summary()
    assert summary["total_questions"] == 3
    assert summary["resolved"] == 2
    assert summary["abandoned"] == 1
    assert summary["pending"] == 0
    assert "理解几分之一" in summary["covered_key_points"]
    assert "比较大小" in summary["covered_key_points"]
    assert "m_001" in summary["broken_misconception_ids"]
    assert summary["resolution_sources"]["self_resolve"] == 1
    assert summary["resolution_sources"]["teacher_marked"] == 1
    assert summary["resolution_sources"]["abandoned"] == 1


async def test_spawn_resilient_to_one_student_failure() -> None:
    """一个学生 generate_questions 抛异常，其余仍正常入队。"""
    bad = FakeStudentAgent(
        student_id="bad",
        name="坏学生",
        questions=[{"content": "X"}],
        fail_on_generate=True,
    )
    good = FakeStudentAgent(
        student_id="good",
        name="好学生",
        questions=[{"content": "G1"}],
    )
    session = QASession(lesson_meta=_lesson())
    questions = await session.spawn([bad, good], questions_per_student=1)
    assert len(questions) == 1
    assert questions[0].speaker_id == "good"


async def test_get_dialog_unknown_id_raises() -> None:
    session = QASession(lesson_meta=_lesson())
    with pytest.raises(QASessionError):
        session.get_dialog("nonexistent")


async def test_iter_students_yields_spawn_order() -> None:
    """``iter_students`` 应按 spawn 注册顺序遍历 (student_id, agent)。

    这是 REST / WS 投影层的公开访问器，替代直接读 ``_agents`` 私有字段。
    顺序由 spawn 入参决定，dict 维持插入顺序。
    """
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],
    )
    b = FakeStudentAgent(
        student_id="B",
        name="学生B",
        questions=[{"content": "B1"}],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a, b], questions_per_student=1)

    pairs = list(session.iter_students())
    assert [sid for sid, _ in pairs] == ["A", "B"]
    assert pairs[0][1] is a
    assert pairs[1][1] is b
    # 暴露的 agent 应当是原对象，可以直接读 .persona
    assert pairs[0][1].persona.name == "学生A"


async def test_iter_students_empty_before_spawn() -> None:
    """``iter_students`` 在 spawn 之前应当为空。"""
    session = QASession(lesson_meta=_lesson())
    assert list(session.iter_students()) == []
