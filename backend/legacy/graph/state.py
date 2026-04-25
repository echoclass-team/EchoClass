"""Classroom graph state and serialization helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from pydantic import BaseModel, TypeAdapter

from legacy.schemas.director import DirectorDecision, Message
from legacy.schemas.events import AgentEventModel
from schemas.lesson import LessonMeta
from schemas.stage import StageProfile
from schemas.student import Persona


class PendingQuestion(BaseModel):
    speaker_id: str
    content: str
    created_at_seconds: int


class ClassroomState(TypedDict):
    session_id: str
    lesson_meta: LessonMeta
    stage: StageProfile
    students: list[Persona]
    transcript: list[Message]
    blackboard: list[str]
    taught_points: set[str]
    pending_questions: list[PendingQuestion]
    director_history: list[DirectorDecision]
    elapsed_seconds: int
    started_at: datetime
    event_seq: int
    turn_index: int
    last_teacher_utterance: str | None
    incoming_teacher_utterance: str | None
    pending_events: list[AgentEventModel]


_event_adapter = TypeAdapter(AgentEventModel)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def state_to_jsonable(state: ClassroomState) -> dict[str, Any]:
    return _jsonable(dict(state))


def state_from_jsonable(data: dict[str, Any]) -> ClassroomState:
    return ClassroomState(
        session_id=data["session_id"],
        lesson_meta=LessonMeta(**data["lesson_meta"]),
        stage=StageProfile(**data["stage"]),
        students=[Persona(**s) for s in data.get("students", [])],
        transcript=[Message(**m) for m in data.get("transcript", [])],
        blackboard=list(data.get("blackboard", [])),
        taught_points=set(data.get("taught_points", [])),
        pending_questions=[
            PendingQuestion(**q) for q in data.get("pending_questions", [])
        ],
        director_history=[
            DirectorDecision(**d) for d in data.get("director_history", [])
        ],
        elapsed_seconds=int(data.get("elapsed_seconds", 0)),
        started_at=datetime.fromisoformat(data["started_at"]),
        event_seq=int(data.get("event_seq", 0)),
        turn_index=int(data.get("turn_index", 0)),
        last_teacher_utterance=data.get("last_teacher_utterance"),
        incoming_teacher_utterance=data.get("incoming_teacher_utterance"),
        pending_events=[
            _event_adapter.validate_python(e) for e in data.get("pending_events", [])
        ],
    )


def initial_classroom_state(
    *,
    session_id: str,
    lesson_meta: LessonMeta,
    stage: StageProfile,
    students: list[Persona],
    started_at: datetime | None = None,
) -> ClassroomState:
    return ClassroomState(
        session_id=session_id,
        lesson_meta=lesson_meta,
        stage=stage,
        students=students,
        transcript=[],
        blackboard=[],
        taught_points=set(),
        pending_questions=[],
        director_history=[],
        elapsed_seconds=0,
        started_at=started_at or datetime.now(timezone.utc),
        event_seq=0,
        turn_index=0,
        last_teacher_utterance=None,
        incoming_teacher_utterance=None,
        pending_events=[],
    )
