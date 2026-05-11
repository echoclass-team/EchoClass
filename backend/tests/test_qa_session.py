"""QASession orchestrator 集成测试（mock StudentAgent，不调真 LLM）。

覆盖预生成题机制：

- spawn 为每个学生预生成 N 题（默认 3），按学生顺序入队
- next_pending FIFO；start_dialog 后从 pending 队列移除并激活当前题 progress
- send_teacher_message 自动推进子题：self_resolved / turn_limit / 全部完成
- mark_resolved 推进当前子题；abandon_dialog 标记当前 active 子题为 abandoned
- summary 统计；spawn 单一学生失败不影响其他
- question_progress 的 turns_used / message_start_idx / message_end_idx 切片
"""

from __future__ import annotations

from typing import Any

import pytest

from schemas.dialog import DialogReplyResult
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import (
    MAX_TURNS_PER_QUESTION,
    PRESET_QUESTIONS_PER_STUDENT,
    QASession,
    QASessionError,
)


# ============================================================ Fakes


class FakePersona:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeStudentAgent:
    """只提供 QASession 依赖的最小鸭子类型接口。"""

    def __init__(
        self,
        *,
        student_id: str,
        name: str,
        questions: list[dict[str, Any]],
        replies: list[DialogReplyResult] | None = None,
        fail_on_generate: bool = False,
    ) -> None:
        self.persona = FakePersona(name)
        self._student_id = student_id
        self._questions_template = questions
        self._replies = list(replies or [])
        self._fail_on_generate = fail_on_generate
        self.respond_questions: list[str] = []

    async def generate_questions(
        self, lesson_meta: LessonMeta, *, count: int = 3
    ) -> list[StudentQuestion]:
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


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数",
        objectives=[],
        key_points=["理解几分之一", "比较大小"],
        difficult_points=["平均分"],
    )


def _three_questions(prefix: str = "Q") -> list[dict[str, Any]]:
    return [
        {"content": f"{prefix}1"},
        {"content": f"{prefix}2"},
        {"content": f"{prefix}3"},
    ]


# ============================================================ tests


async def test_spawn_creates_n_predetermined_questions_per_student() -> None:
    """spawn 默认 N=3：每个学生 1 个 dialog，asked_questions 含 3 题，progress 对齐。"""
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    b = FakeStudentAgent(student_id="B", name="学生B", questions=_three_questions("B"))
    session = QASession(lesson_meta=_lesson())
    first_questions = await session.spawn([a, b])

    # 仅返回首问，不包含后续预生成题
    assert [q.content for q in first_questions] == ["A1", "B1"]
    assert session.pending_count() == 2
    assert list(session.dialogs.keys()) == ["A", "B"]

    dialog_a = session.dialogs["A"]
    assert dialog_a.question.content == "A1"
    assert [q.content for q in dialog_a.asked_questions] == ["A1", "A2", "A3"]
    assert len(dialog_a.question_progress) == 3
    assert all(p.status == "pending" for p in dialog_a.question_progress)
    assert dialog_a.current_question_idx == 0


async def test_spawn_with_explicit_count() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=2)
    dialog = session.dialogs["A"]
    assert len(dialog.asked_questions) == 2
    assert len(dialog.question_progress) == 2


async def test_spawn_invalid_count_raises() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    session = QASession(lesson_meta=_lesson())
    with pytest.raises(QASessionError):
        await session.spawn([a], questions_per_student=0)


async def test_preset_constant_is_three() -> None:
    """合约：N=3 是公开常量，不可悄悄改。"""
    assert PRESET_QUESTIONS_PER_STUDENT == 3
    assert MAX_TURNS_PER_QUESTION == 8


async def test_next_pending_fifo_order() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    b = FakeStudentAgent(student_id="B", name="学生B", questions=_three_questions("B"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a, b])

    first = session.next_pending()
    assert first is not None and first.id == "A"
    session.start_dialog(first.id)

    second = session.next_pending()
    assert second is not None and second.id == "B"
    session.start_dialog(second.id)

    assert session.next_pending() is None


async def test_start_dialog_activates_first_question_progress() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    session.start_dialog("A")

    dialog = session.get_dialog("A")
    assert dialog.status == "active"
    assert dialog.question_progress[0].status == "active"
    assert dialog.question_progress[0].message_start_idx == 0
    # 后续题保持 pending
    assert dialog.question_progress[1].status == "pending"


async def test_send_teacher_message_records_history() -> None:
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=[DialogReplyResult(content="哦。", self_resolved=False)],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None

    result = await session.send_teacher_message(pending.id, "讲解 A1")
    assert result.content == "哦。"
    dialog = session.get_dialog(pending.id)
    assert dialog.status == "active"
    assert [m.role for m in dialog.messages] == ["teacher", "student"]
    # 当前题 turns_used+=1，但还没推进
    assert dialog.current_question_idx == 0
    assert dialog.question_progress[0].turns_used == 1
    assert dialog.question_progress[0].status == "active"


async def test_self_resolved_advances_to_next_question() -> None:
    """学生说 [懂了] → 当前题标 resolved(self_resolve)，自动抛下一题为 is_new_question。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=[DialogReplyResult(content="懂了！", self_resolved=True)],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None

    result = await session.send_teacher_message(pending.id, "讲解 A1")
    assert result.self_resolved is True

    dialog = session.get_dialog(pending.id)
    # 当前题 resolved
    assert dialog.question_progress[0].status == "resolved"
    assert dialog.question_progress[0].resolution_source == "self_resolve"
    assert dialog.question_progress[0].message_end_idx == 2  # teacher + student
    # 推进到第 2 题
    assert dialog.current_question_idx == 1
    assert dialog.question_progress[1].status == "active"
    assert dialog.question_progress[1].message_start_idx == 2
    # is_new_question 消息已 append
    assert [m.role for m in dialog.messages] == ["teacher", "student", "student"]
    new_q_msg = dialog.messages[-1]
    assert new_q_msg.is_new_question is True
    assert new_q_msg.content == "A2"
    assert new_q_msg.question_id == dialog.asked_questions[1].id
    # dialog 整体仍 active
    assert dialog.status == "active"


async def test_turn_limit_advances_with_abandoned_source() -> None:
    """连续 M 轮没说懂 → 当前题 abandoned(turn_limit)，自动推进。"""
    # 8 轮都没 self_resolved
    replies = [
        DialogReplyResult(content=f"嗯{i}", self_resolved=False)
        for i in range(MAX_TURNS_PER_QUESTION)
    ]
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=replies,
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None

    for i in range(MAX_TURNS_PER_QUESTION):
        await session.send_teacher_message(pending.id, f"讲第{i}遍")

    dialog = session.get_dialog(pending.id)
    assert dialog.question_progress[0].status == "abandoned"
    assert dialog.question_progress[0].resolution_source == "turn_limit"
    assert dialog.current_question_idx == 1
    # 最后一条是 is_new_question
    assert dialog.messages[-1].is_new_question is True
    assert dialog.messages[-1].content == "A2"


async def test_all_questions_resolved_closes_dialog() -> None:
    """3 题都自我解决 → dialog 整体 resolved。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=[
            DialogReplyResult(content="懂了1", self_resolved=True),
            DialogReplyResult(content="懂了2", self_resolved=True),
            DialogReplyResult(content="懂了3", self_resolved=True),
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None

    await session.send_teacher_message(pending.id, "T1")
    dialog = session.get_dialog(pending.id)
    assert dialog.current_question_idx == 1 and dialog.status == "active"

    await session.send_teacher_message(pending.id, "T2")
    assert dialog.current_question_idx == 2 and dialog.status == "active"

    await session.send_teacher_message(pending.id, "T3")
    # 第 3 题也 resolved → 整 dialog resolved
    assert dialog.status == "resolved"
    assert dialog.resolution_source == "self_resolve"
    assert dialog.current_question_idx == 3  # 越过最后一题
    assert all(p.status == "resolved" for p in dialog.question_progress)


async def test_send_message_on_resolved_dialog_raises() -> None:
    """所有题都做完后，dialog 已 resolved，再发消息应抛错。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=[{"content": "A1"}],  # 仅 1 题
        replies=[DialogReplyResult(content="懂了！", self_resolved=True)],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    pending = session.next_pending()
    assert pending is not None

    await session.send_teacher_message(pending.id, "讲")
    assert session.get_dialog(pending.id).status == "resolved"

    with pytest.raises(QASessionError):
        await session.send_teacher_message(pending.id, "再问")


async def test_self_resolved_marker_lands_on_student_message() -> None:
    """self_resolved=True 应同时落到 dialog.messages 上，便于 GET 复原。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=[DialogReplyResult(content="懂了！", self_resolved=True)],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None

    await session.send_teacher_message(pending.id, "讲")
    dialog = session.get_dialog(pending.id)
    # messages: [teacher, student(self_resolved=True), student(is_new_question=True)]
    assert dialog.messages[1].role == "student"
    assert dialog.messages[1].self_resolved is True


async def test_mark_resolved_advances_current_question() -> None:
    """老师手动 mark_resolved → 当前题 resolved(teacher_marked)，推进下一题。"""
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    session.start_dialog("A")

    dialog = session.mark_resolved("A", source="teacher_marked")
    assert dialog.current_question_idx == 1
    assert dialog.question_progress[0].status == "resolved"
    assert dialog.question_progress[0].resolution_source == "teacher_marked"
    assert dialog.question_progress[1].status == "active"
    assert dialog.status == "active"  # 还有题


async def test_mark_resolved_on_last_question_closes_dialog() -> None:
    """对最后一题 mark_resolved → 整个 dialog resolved。"""
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    session.start_dialog("A")

    session.mark_resolved("A", source="teacher_marked")
    session.mark_resolved("A", source="teacher_marked")
    session.mark_resolved("A", source="teacher_marked")

    dialog = session.get_dialog("A")
    assert dialog.status == "resolved"
    assert dialog.resolution_source == "teacher_marked"


async def test_mark_resolved_idempotent_on_finished_dialog() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=[{"content": "A1"}])
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a], questions_per_student=1)
    session.start_dialog("A")

    session.mark_resolved("A", source="teacher_marked")
    # 再次调用是幂等的，不抛错
    dialog = session.mark_resolved("A", source="self_resolve")
    assert dialog.status == "resolved"
    # source 不被覆盖
    assert dialog.resolution_source == "teacher_marked"


async def test_mark_resolved_after_abandoned_raises() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    session.abandon_dialog("A")
    with pytest.raises(QASessionError):
        session.mark_resolved("A")


async def test_abandon_dialog_marks_current_active_question() -> None:
    """abandon_dialog 整 dialog 标 abandoned，并把当前 active 子题也标 abandoned。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=[DialogReplyResult(content="嗯", self_resolved=False)],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None
    await session.send_teacher_message(pending.id, "讲")

    dialog = session.abandon_dialog("A")
    assert dialog.status == "abandoned"
    assert dialog.resolution_source == "abandoned"
    # 当前 active 题也被关闭
    assert dialog.question_progress[0].status == "abandoned"
    assert dialog.question_progress[0].resolution_source == "abandoned"
    assert dialog.question_progress[0].message_end_idx == 2
    # 未开启的题保持 pending
    assert dialog.question_progress[1].status == "pending"


async def test_question_progress_message_indices_track_segments() -> None:
    """progress.message_start_idx / end_idx 应正确切片每题的 messages。"""
    a = FakeStudentAgent(
        student_id="A",
        name="学生A",
        questions=_three_questions("A"),
        replies=[
            DialogReplyResult(content="嗯1", self_resolved=False),
            DialogReplyResult(content="懂了！", self_resolved=True),
            DialogReplyResult(content="懂了2", self_resolved=True),
        ],
    )
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a])
    pending = session.next_pending()
    assert pending is not None

    # 第 1 题：teacher + student(嗯1) + teacher + student(懂了!) → 4 条
    await session.send_teacher_message(pending.id, "T1-1")
    await session.send_teacher_message(pending.id, "T1-2")
    # 第 2 题已被自动抛出（is_new_question），messages 含 5 条
    # 接下来对第 2 题: teacher + student(懂了2) → +2 条 = 7 条
    await session.send_teacher_message(pending.id, "T2-1")

    dialog = session.get_dialog(pending.id)
    p0 = dialog.question_progress[0]
    p1 = dialog.question_progress[1]
    assert p0.message_start_idx == 0
    assert p0.message_end_idx == 4  # 第 1 题占据 [0, 4)
    assert p1.message_start_idx == 4  # 第 2 题从 is_new_question 起
    # 第 2 题 resolved 后 end_idx 应为推进时的 messages 长度
    assert p1.message_end_idx is not None
    # 切片完整性：messages[start:end] 应能回放该题对话
    seg0 = dialog.messages[p0.message_start_idx : p0.message_end_idx]
    assert [m.role for m in seg0] == ["teacher", "student", "teacher", "student"]


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
            {"content": "B1", "linked_key_point": "比较大小"},
        ],
    )
    c = FakeStudentAgent(student_id="C", name="学生C", questions=[{"content": "C1"}])
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a, b, c], questions_per_student=1)

    session.start_dialog("A")
    session.start_dialog("B")
    session.start_dialog("C")
    session.mark_resolved("A", source="self_resolve")
    session.mark_resolved("B", source="teacher_marked")
    session.abandon_dialog("C")

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
    bad = FakeStudentAgent(
        student_id="bad",
        name="坏学生",
        questions=[{"content": "X"}],
        fail_on_generate=True,
    )
    good = FakeStudentAgent(
        student_id="good", name="好学生", questions=_three_questions("G")
    )
    session = QASession(lesson_meta=_lesson())
    questions = await session.spawn([bad, good])
    assert len(questions) == 1
    assert questions[0].speaker_id == "good"


async def test_get_dialog_unknown_id_raises() -> None:
    session = QASession(lesson_meta=_lesson())
    with pytest.raises(QASessionError):
        session.get_dialog("nonexistent")


async def test_iter_students_yields_spawn_order() -> None:
    a = FakeStudentAgent(student_id="A", name="学生A", questions=_three_questions("A"))
    b = FakeStudentAgent(student_id="B", name="学生B", questions=_three_questions("B"))
    session = QASession(lesson_meta=_lesson())
    await session.spawn([a, b])

    pairs = list(session.iter_students())
    assert [sid for sid, _ in pairs] == ["A", "B"]
    assert pairs[0][1] is a


async def test_iter_students_empty_before_spawn() -> None:
    session = QASession(lesson_meta=_lesson())
    assert list(session.iter_students()) == []
