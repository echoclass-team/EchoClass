"""Minimal internal graph event schemas shared by graph core and future WS transport.

The wire serializer/envelope is intentionally left to issue #25 so these models
stay as the graph-owned canonical payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field
from legacy.schemas.student_reply import Intent


class BaseAgentEvent(BaseModel):
    type: str
    session_id: str
    event_seq: int = Field(..., ge=1, alias="seq")
    created_at: datetime

    model_config = {"populate_by_name": True}


class DirectorEvent(BaseAgentEvent):
    type: Literal["director_event"] = "director_event"
    event: Literal["hand_raise", "distraction", "student_speak", "silent"]
    speaker_id: str | None = None
    description: str
    rationale: str | None = None


class StudentReplyStartEvent(BaseAgentEvent):
    type: Literal["student_reply_start"] = "student_reply_start"
    reply_id: str
    speaker_id: str
    intent: Intent
    emotion: str
    trigger: Literal["teacher_prompt", "spontaneous", "peer_reaction"]
    started_at: datetime


class StudentReplyChunkEvent(BaseAgentEvent):
    type: Literal["student_reply_chunk"] = "student_reply_chunk"
    reply_id: str
    speaker_id: str
    delta: str
    chunk_seq: int = Field(..., ge=0)


class StudentReplyEndEvent(BaseAgentEvent):
    type: Literal["student_reply_end"] = "student_reply_end"
    reply_id: str
    speaker_id: str
    full_content: str
    intent: Intent
    emotion: str
    ended_at: datetime
    triggered_misconception_id: str | None = None


class BoardUpdateEvent(BaseAgentEvent):
    type: Literal["board_update"] = "board_update"
    taught_points: list[str]


class SessionEndEvent(BaseAgentEvent):
    type: Literal["session_end"] = "session_end"
    reason: str
    duration_seconds: int | None = None
    summary_url: str | None = None


AgentEvent: TypeAlias = Annotated[
    DirectorEvent
    | StudentReplyStartEvent
    | StudentReplyChunkEvent
    | StudentReplyEndEvent
    | BoardUpdateEvent
    | SessionEndEvent,
    Field(discriminator="type"),
]
AgentEventModel: TypeAlias = AgentEvent
