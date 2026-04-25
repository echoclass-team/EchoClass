from __future__ import annotations

import asyncio

import pytest

from graph.classroom import ClassroomGraph, build_classroom_graph
from graph.checkpoint import SQLiteCheckpointStore
from graph.state import initial_classroom_state, state_from_jsonable, state_to_jsonable
from schemas.director import DirectorDecision, StudentAction
from schemas.events import DirectorEvent
from schemas.lesson import LessonMeta
from schemas.stage import StageProfile
from schemas.student import Persona, StudentReply


class FakeDirector:
    async def decide(self, teacher_utterance, stage, students, history, elapsed_seconds):
        student = students[elapsed_seconds % len(students)]
        return DirectorDecision(
            actions=[StudentAction(speaker_id=student.id, action_type="speak", priority=5)],
            next_action_delay_ms=1000,
            rationale="fake rotation",
        )


class FakeStudentAgent:
    def __init__(self, *, persona, **kwargs):
        self.persona = persona

    async def respond(self, teacher_utterance: str) -> StudentReply:
        intent = "ask_question" if "?" in teacher_utterance or "？" in teacher_utterance else "answer_question"
        return StudentReply(
            speaker_id=self.persona.id,
            intent=intent,
            content=f"{self.persona.name}回答：我理解了分数，也想比较大小。",
            emotion="自信",
        )


class FakeMisconceptionStudentAgent:
    def __init__(self, *, persona, context, **kwargs):
        self.persona = persona
        self.context = context

    async def respond(self, teacher_utterance: str) -> StudentReply:
        assert self.context.key_points == ["分数", "比较大小"]
        return StudentReply(
            speaker_id=self.persona.id,
            intent="answer_question",
            content="我觉得大小不一样也可以叫二分之一。",
            emotion="困惑",
            triggered_misconception_id="math_fraction_average_01",
        )


def fake_factory(**kwargs):
    return FakeStudentAgent(**kwargs)


def misconception_factory(**kwargs):
    return FakeMisconceptionStudentAgent(**kwargs)


@pytest.fixture
def lesson():
    return LessonMeta(subject="数学", grade="三年级", topic="分数", key_points=["分数", "比较大小"])


@pytest.fixture
def stage():
    return StageProfile(
        id="p_middle",
        name="小学中年级",
        grade_range="P3-P4",
        age_range="8-10",
        piaget_stage="具体运算",
        thinking_style="具体形象",
        language_style="简洁",
        attention_features="稳定",
        memory_features="形象记忆",
        erikson_stage="勤奋感",
        self_awareness="发展中",
        peer_relationship="合作",
    )


@pytest.fixture
def students():
    return [
        Persona(id=f"s{i}", name=f"学生{i}", personality="活泼", knowledge_level="中等", behavior_traits="积极", stage_id="p_middle")
        for i in range(3)
    ]


@pytest.mark.asyncio
async def test_classroom_graph_runs_20_turns_with_ordered_events(lesson, stage, students):
    queue: asyncio.Queue = asyncio.Queue()
    graph = ClassroomGraph(director=FakeDirector(), student_agent_factory=fake_factory, event_queue=queue, chunk_size=6)
    assert graph.state_graph is not None
    assert hasattr(graph.state_graph, "ainvoke")
    state = initial_classroom_state(session_id="sess-1", lesson_meta=lesson, stage=stage, students=students)

    for i in range(20):
        state = await graph.run_turn(state, f"第{i}轮讲分数？")

    assert len([m for m in state["transcript"] if m.role == "teacher"]) == 20
    assert len([m for m in state["transcript"] if m.role == "student"]) == 20
    assert len(state["director_history"]) == 20
    assert state["taught_points"] == {"分数", "比较大小"}
    assert state["blackboard"] == ["分数", "比较大小"]
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert [e.event_seq for e in events] == sorted(e.event_seq for e in events)
    director_indices = [i for i, e in enumerate(events) if e.type == "director_event"]
    assert len(director_indices) == 20
    for pos, director_idx in enumerate(director_indices):
        next_director = director_indices[pos + 1] if pos + 1 < len(director_indices) else len(events)
        assert any(e.type == "student_reply_start" for e in events[director_idx + 1 : next_director])


@pytest.mark.asyncio
async def test_sqlite_restore_continues_without_losing_messages(tmp_path, lesson, stage, students):
    store = SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite")
    queue: asyncio.Queue = asyncio.Queue()
    graph = ClassroomGraph(director=FakeDirector(), student_agent_factory=fake_factory, checkpoint_store=store, event_queue=queue)
    state = initial_classroom_state(session_id="sess-2", lesson_meta=lesson, stage=stage, students=students)
    for i in range(5):
        state = await graph.run_turn(state, f"先学分数 {i}")

    restored = await graph.restore("sess-2")
    assert restored is not None
    assert restored["turn_index"] == 5
    assert restored["event_seq"] > 0
    assert restored["pending_events"] == []
    graph2 = ClassroomGraph(director=FakeDirector(), student_agent_factory=fake_factory, checkpoint_store=store, event_queue=queue)
    for i in range(5, 20):
        restored = await graph2.run_turn(restored, f"继续学分数 {i}")

    assert len(restored["transcript"]) == 40
    assert restored["turn_index"] == 20
    assert restored["event_seq"] > state["event_seq"]


def test_state_serialization_roundtrip_handles_models_sets_and_events(lesson, stage, students):
    state = initial_classroom_state(session_id="sess-3", lesson_meta=lesson, stage=stage, students=students)
    state["taught_points"].add("分数")
    state["pending_events"].append(
        DirectorEvent(session_id="sess-3", event_seq=1, created_at=state["started_at"], event="student_speak", speaker_id="s0", description="s0 speak")
    )
    restored = state_from_jsonable(state_to_jsonable(state))
    assert restored["started_at"] == state["started_at"]
    assert restored["taught_points"] == {"分数"}
    assert restored["pending_events"][0].type == "director_event"


@pytest.mark.asyncio
async def test_restored_state_flushes_pending_events_before_next_turn(tmp_path, lesson, stage, students):
    store = SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite")
    graph = ClassroomGraph(director=FakeDirector(), student_agent_factory=fake_factory, checkpoint_store=store, event_queue=asyncio.Queue())
    state = initial_classroom_state(session_id="sess-4", lesson_meta=lesson, stage=stage, students=students)
    state["pending_events"].append(
        DirectorEvent(session_id="sess-4", event_seq=1, created_at=state["started_at"], event="student_speak", speaker_id="s0", description="crash before wait")
    )
    state["event_seq"] = 1
    await store.save_checkpoint("sess-4", state, node="persist", event_seq=state["event_seq"])

    restored = await graph.restore("sess-4")
    assert restored is not None
    assert restored["pending_events"]

    resume_queue: asyncio.Queue = asyncio.Queue()
    resumed_graph = ClassroomGraph(
        director=FakeDirector(),
        student_agent_factory=fake_factory,
        checkpoint_store=store,
        event_queue=resume_queue,
    )
    restored = await resumed_graph.run_turn(restored, "继续讲分数")

    events = []
    while not resume_queue.empty():
        events.append(resume_queue.get_nowait())
    assert events[0].event_seq == 1
    assert any(event.event_seq > 1 for event in events)
    assert restored["pending_events"] == []


@pytest.mark.asyncio
async def test_wait_checkpoint_prevents_duplicate_events_after_restore(tmp_path, lesson, stage, students):
    store = SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite")
    first_queue: asyncio.Queue = asyncio.Queue()
    graph = ClassroomGraph(director=FakeDirector(), student_agent_factory=fake_factory, checkpoint_store=store, event_queue=first_queue)
    state = initial_classroom_state(session_id="sess-5", lesson_meta=lesson, stage=stage, students=students)
    state = await graph.run_turn(state, "先讲分数")
    first_events = []
    while not first_queue.empty():
        first_events.append(first_queue.get_nowait())

    restored = await graph.restore("sess-5")
    assert restored is not None
    assert restored["pending_events"] == []

    second_queue: asyncio.Queue = asyncio.Queue()
    resumed = ClassroomGraph(director=FakeDirector(), student_agent_factory=fake_factory, checkpoint_store=store, event_queue=second_queue)
    restored = await resumed.run_turn(restored, "继续讲分数")
    second_events = []
    while not second_queue.empty():
        second_events.append(second_queue.get_nowait())

    assert second_events
    assert {e.event_seq for e in first_events}.isdisjoint({e.event_seq for e in second_events})
    assert restored["pending_events"] == []


def test_build_classroom_graph_returns_compiled_graph() -> None:
    graph = build_classroom_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_student_reply_end_event_keeps_triggered_misconception_id(lesson, stage, students):
    queue: asyncio.Queue = asyncio.Queue()
    graph = ClassroomGraph(
        director=FakeDirector(),
        student_agent_factory=misconception_factory,
        event_queue=queue,
    )
    state = initial_classroom_state(
        session_id="sess-misconception",
        lesson_meta=lesson,
        stage=stage,
        students=students,
    )

    await graph.run_turn(state, "什么是二分之一？")

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    end_events = [event for event in events if event.type == "student_reply_end"]
    assert end_events
    assert end_events[0].triggered_misconception_id == "math_fraction_average_01"
