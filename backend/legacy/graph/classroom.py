"""A-owned classroom graph core."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

try:  # LangGraph is optional at execution time for stable unit tests.
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover
    END = "__end__"  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]

from agents.student import StudentAgent
from legacy.graph.checkpoint import CheckpointStore, InMemoryCheckpointStore
from legacy.graph.state import ClassroomState, PendingQuestion
from legacy.schemas.director import DirectorDecision, Message, StudentAction
from legacy.schemas.events import (
    AgentEventModel,
    BoardUpdateEvent,
    DirectorEvent,
    StudentReplyChunkEvent,
    StudentReplyEndEvent,
    StudentReplyStartEvent,
)
from schemas.student import ClassroomContext, Persona, StudentReply

StudentAgentFactory = Callable[..., Any]


def build_classroom_graph(
    node_mapping: Mapping[str, Callable[[ClassroomState], Any]] | None = None,
) -> Any:
    if StateGraph is None:
        return None
    graph = StateGraph(ClassroomState)

    async def passthrough(state: ClassroomState) -> ClassroomState:
        return state

    nodes = node_mapping or {
        node: passthrough
        for node in (
            "teacher_input",
            "director",
            "fanout_students",
            "aggregate",
            "persist",
            "wait",
        )
    }
    for node in (
        "teacher_input",
        "director",
        "fanout_students",
        "aggregate",
        "persist",
        "wait",
    ):
        graph.add_node(node, nodes[node])
    graph.set_entry_point("teacher_input")
    graph.add_edge("teacher_input", "director")
    graph.add_edge("director", "fanout_students")
    graph.add_edge("fanout_students", "aggregate")
    graph.add_edge("aggregate", "persist")
    graph.add_edge("persist", "wait")
    graph.add_edge("wait", END)
    return graph.compile()


class ClassroomGraph:
    def __init__(
        self,
        *,
        director: Any,
        llm: Any | None = None,
        student_agent_factory: StudentAgentFactory | None = None,
        checkpoint_store: CheckpointStore | None = None,
        event_queue: asyncio.Queue[AgentEventModel] | None = None,
        chunk_size: int = 8,
    ) -> None:
        self.director = director
        self.llm = llm
        self.student_agent_factory = (
            student_agent_factory or self._default_student_agent_factory
        )
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.event_queue = event_queue
        self.chunk_size = chunk_size
        self._student_replies: list[StudentReply] = []
        self.state_graph = build_classroom_graph(
            {
                "teacher_input": self.teacher_input_node,
                "director": self.director_node,
                "fanout_students": self.fanout_students_node,
                "aggregate": self.aggregate_node,
                "persist": self.persist_node,
                "wait": self.wait_node,
            }
        )

    async def run_turn(
        self, state: ClassroomState, teacher_utterance: str
    ) -> ClassroomState:
        # Restored checkpoints are saved after ``persist`` and before ``wait``.
        # Resume by flushing that outbox first, then accept the next teacher input.
        if state["pending_events"]:
            state = await self.wait_node(state)
        state["incoming_teacher_utterance"] = teacher_utterance
        if self.state_graph is None:
            state = await self.teacher_input_node(state)
            state = await self.director_node(state)
            state = await self.fanout_students_node(state)
            state = await self.aggregate_node(state)
            state = await self.persist_node(state)
            return await self.wait_node(state)
        return await self.state_graph.ainvoke(state)

    async def teacher_input_node(self, state: ClassroomState) -> ClassroomState:
        teacher_utterance = state.get("incoming_teacher_utterance")
        if teacher_utterance is None:
            return state
        state["turn_index"] += 1
        state["last_teacher_utterance"] = teacher_utterance
        state["incoming_teacher_utterance"] = None
        state["transcript"].append(
            Message(
                role="teacher",
                speaker_id="teacher",
                content=teacher_utterance,
                timestamp_seconds=state["elapsed_seconds"],
            )
        )
        self._mark_taught_points(state, teacher_utterance)
        return state

    async def director_node(self, state: ClassroomState) -> ClassroomState:
        decision: DirectorDecision = await self.director.decide(
            state["last_teacher_utterance"] or "",
            state["stage"],
            state["students"],
            state["transcript"],
            state["elapsed_seconds"],
        )
        state["director_history"].append(decision)
        mapping = {
            "raise_hand": "hand_raise",
            "daydream": "distraction",
            "speak": "student_speak",
            "silent": "silent",
        }
        for action in decision.actions:
            state["pending_events"].append(
                self._next_event(
                    state,
                    DirectorEvent,
                    event=mapping[action.action_type],
                    speaker_id=action.speaker_id,
                    description=f"{action.speaker_id} {action.action_type}",
                    rationale=decision.rationale,
                )
            )
        return state

    async def fanout_students_node(self, state: ClassroomState) -> ClassroomState:
        actions = (
            state["director_history"][-1].actions if state["director_history"] else []
        )
        speak_actions = [a for a in actions if a.action_type == "speak"]

        async def call(action: StudentAction) -> StudentReply:
            persona = self._find_student(state["students"], action.speaker_id)
            history = [f"{m.role}:{m.content}" for m in state["transcript"][-12:]]
            context = ClassroomContext(
                subject=state["lesson_meta"].subject,
                topic=state["lesson_meta"].topic,
                history=history,
                key_points=state["lesson_meta"].key_points,
                difficult_points=state["lesson_meta"].difficult_points,
            )
            agent = self.student_agent_factory(
                llm=self.llm, persona=persona, context=context, stage=state["stage"]
            )
            return await agent.respond(state["last_teacher_utterance"] or "")

        self._student_replies = (
            await asyncio.gather(*(call(a) for a in speak_actions))
            if speak_actions
            else []
        )
        return state

    async def aggregate_node(self, state: ClassroomState) -> ClassroomState:
        board_before = set(state["taught_points"])
        for reply in self._student_replies:
            state["transcript"].append(
                Message(
                    role="student",
                    speaker_id=reply.speaker_id,
                    content=reply.content,
                    timestamp_seconds=state["elapsed_seconds"],
                )
            )
            if reply.intent == "ask_question":
                state["pending_questions"].append(
                    PendingQuestion(
                        speaker_id=reply.speaker_id,
                        content=reply.content,
                        created_at_seconds=state["elapsed_seconds"],
                    )
                )
            self._append_reply_events(state, reply)
            self._mark_taught_points(state, reply.content)
        if state["taught_points"] != board_before:
            state["pending_events"].append(
                self._next_event(
                    state,
                    BoardUpdateEvent,
                    taught_points=sorted(state["taught_points"]),
                )
            )
        state["elapsed_seconds"] += 1
        return state

    async def persist_node(self, state: ClassroomState) -> ClassroomState:
        await self.checkpoint_store.save_checkpoint(
            state["session_id"], state, node="persist", event_seq=state["event_seq"]
        )
        return state

    async def wait_node(self, state: ClassroomState) -> ClassroomState:
        if self.event_queue is not None:
            for event in state["pending_events"]:
                await self.event_queue.put(event)
            state["pending_events"] = []
            await self.checkpoint_store.save_checkpoint(
                state["session_id"], state, node="wait", event_seq=state["event_seq"]
            )
        return state

    async def restore(self, session_id: str) -> ClassroomState | None:
        return await self.checkpoint_store.load_latest(session_id)

    def _default_student_agent_factory(self, **kwargs: Any) -> StudentAgent:
        return StudentAgent(**kwargs)

    def _next_event(
        self, state: ClassroomState, cls: type, **kwargs: Any
    ) -> AgentEventModel:
        state["event_seq"] += 1
        return cls(
            session_id=state["session_id"],
            event_seq=state["event_seq"],
            created_at=datetime.now(timezone.utc),
            **kwargs,
        )

    def _append_reply_events(self, state: ClassroomState, reply: StudentReply) -> None:
        now = datetime.now(timezone.utc)
        reply_id = f"{state['session_id']}-{state['turn_index']}-{reply.speaker_id}"
        state["pending_events"].append(
            self._next_event(
                state,
                StudentReplyStartEvent,
                reply_id=reply_id,
                speaker_id=reply.speaker_id,
                intent=reply.intent,
                emotion=reply.emotion,
                trigger="teacher_prompt",
                started_at=now,
            )
        )
        for i in range(0, len(reply.content), self.chunk_size):
            state["pending_events"].append(
                self._next_event(
                    state,
                    StudentReplyChunkEvent,
                    reply_id=reply_id,
                    speaker_id=reply.speaker_id,
                    delta=reply.content[i : i + self.chunk_size],
                    chunk_seq=i // self.chunk_size,
                )
            )
        state["pending_events"].append(
            self._next_event(
                state,
                StudentReplyEndEvent,
                reply_id=reply_id,
                speaker_id=reply.speaker_id,
                full_content=reply.content,
                intent=reply.intent,
                emotion=reply.emotion,
                ended_at=datetime.now(timezone.utc),
                triggered_misconception_id=reply.triggered_misconception_id,
            )
        )

    def _mark_taught_points(self, state: ClassroomState, text: str) -> None:
        for point in state["lesson_meta"].key_points:
            if point and point in text and point not in state["taught_points"]:
                state["taught_points"].add(point)
                state["blackboard"].append(point)

    def _find_student(self, students: list[Persona], speaker_id: str) -> Persona:
        for student in students:
            if student.id == speaker_id or student.name == speaker_id:
                return student
        raise ValueError(f"student not found: {speaker_id}")
