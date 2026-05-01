"""``/ws/qa-sessions/{session_id}`` 端到端集成测试 (#71)。

用 FastAPI TestClient 的同步 WebSocket API + dependency_overrides 注入隔离的
``QASessionRegistry``，无需真实 LLM。

覆盖场景：
- 连上后立即收到 ``session_init``（含 lesson / students / questions）
- ``select_dialog`` → ``dialog_active``
- ``teacher_message`` → ``reply_chunk × N`` → ``reply_end``（含 self_resolved）
- ``resolve`` → ``dialog_resolved``
- ``abandon`` → ``dialog_abandoned``
- 选不存在的 dialog → ``error{code:dialog_not_found}``
- session_id 不存在 → 关闭码 4004
- 客户端发畸形 JSON → ``error{code:invalid_message}``，连接保持
- 同 session 第二次连接挤掉旧连接（``error{code:replaced}``）
- 服务端 seq 单调递增；reply_chunk.chunk_seq 同 dialog 内单调
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.qa_ws import get_tracker
from main import app
from schemas.dialog import DialogMessage, DialogReplyResult, StudentStreamEvent
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession
from services.qa_session_registry import QASessionRegistry, get_registry


# ============================================================ Fakes


class _FakePersona:
    def __init__(
        self,
        *,
        name: str,
        stage_id: str = "p_middle",
        subject_level: str = "中等",
        avatar_seed: str = "seed",
        summary: str = "测试学生",
    ) -> None:
        self.name = name
        self.stage_id = stage_id
        self.subject_level = subject_level
        self.avatar_seed = avatar_seed
        self.summary = summary


class _StreamingFakeAgent:
    """Fake StudentAgent：scripted stream events, 不走 LLM。"""

    def __init__(
        self,
        *,
        student_id: str,
        name: str,
        questions: list[dict[str, Any]],
        scripted_streams: list[list[StudentStreamEvent]] | None = None,
    ) -> None:
        self.persona = _FakePersona(name=name)
        self._student_id = student_id
        self._questions_template = questions
        self._streams = list(scripted_streams or [])

    async def generate_questions(self, lesson_meta: LessonMeta, *, count: int = 3):
        out: list[StudentQuestion] = []
        for i, q in enumerate(self._questions_template[:count]):
            out.append(
                StudentQuestion(
                    id=f"{self._student_id}-q{i}",
                    speaker_id=self._student_id,
                    speaker_name=self.persona.name,
                    content=q.get("content", f"问题{i}"),
                    category="clarify_concept",
                    difficulty="easy",
                    rationale="",
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
        if not self._streams:
            yield StudentStreamEvent(
                type="final",
                result=DialogReplyResult(content="嗯", self_resolved=False, raw="嗯"),
            )
            return
        for evt in self._streams.pop(0):
            yield evt


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数",
        objectives=["理解分数"],
        key_points=["几分之一"],
        difficult_points=[],
    )


# ========================================================== fixtures


@pytest.fixture
def isolated_registry() -> QASessionRegistry:
    """每个测试一份隔离 registry，避免互相污染。"""
    return QASessionRegistry()


@pytest.fixture
def client(isolated_registry: QASessionRegistry):
    """注入隔离 registry，并在测试结束时清掉 connection tracker 状态。"""
    app.dependency_overrides[get_registry] = lambda: isolated_registry
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_registry, None)
        # 清空 _ConnectionTracker 内部状态防止跨测试干扰
        tracker = get_tracker()
        tracker._active.clear()  # noqa: SLF001


async def _build_session(
    registry: QASessionRegistry,
    *,
    scripted_streams: list[list[StudentStreamEvent]] | None = None,
    student_count: int = 1,
) -> QASession:
    agents: list[_StreamingFakeAgent] = []
    for i in range(student_count):
        agent_streams = scripted_streams
        if student_count > 1 and scripted_streams is not None:
            agent_streams = [scripted_streams[i]] if i < len(scripted_streams) else None
        agents.append(
            _StreamingFakeAgent(
                student_id=f"S{i + 1}",
                name="小明" if i == 0 else f"学生{i + 1}",
                questions=[{"content": f"Q{i + 1}"}],
                scripted_streams=agent_streams,
            )
        )
    session = QASession(lesson_meta=_lesson(), session_id="sess-test")
    await session.spawn(agents, questions_per_student=2)
    await registry.register(session)
    return session


def _recv(ws) -> dict[str, Any]:
    """收一条文本帧并解析为 dict。"""
    raw = ws.receive_text()
    return json.loads(raw)


def _send(ws, payload: dict[str, Any]) -> None:
    ws.send_text(json.dumps(payload))


# ============================================================ tests


async def test_session_init_emitted_on_connect(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        msg = _recv(ws)
        assert msg["type"] == "session_init"
        assert msg["seq"] == 0
        assert msg["session_id"] == session.id
        assert msg["lesson"]["topic"] == "分数"
        assert len(msg["students"]) == 1
        assert msg["students"][0]["name"] == "小明"
        assert len(msg["questions"]) == 1


async def test_select_dialog_emits_dialog_active(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    dialog_id = next(iter(session.dialogs.keys()))
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)  # session_init
        _send(ws, {"type": "select_dialog", "dialog_id": dialog_id})
        msg = _recv(ws)
        assert msg["type"] == "dialog_active"
        assert msg["dialog_id"] == dialog_id
        assert msg["seq"] == 1


async def test_teacher_message_streams_chunks_then_end(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    final = DialogReplyResult(
        content="哦！我懂了。", self_resolved=True, raw="哦！我懂了。[懂了]"
    )
    session = await _build_session(
        isolated_registry,
        scripted_streams=[
            [
                StudentStreamEvent(type="delta", delta="哦！"),
                StudentStreamEvent(type="delta", delta="我懂了。"),
                StudentStreamEvent(type="final", result=final),
            ]
        ],
    )
    dialog_id = next(iter(session.dialogs.keys()))

    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)  # session_init
        _send(ws, {"type": "select_dialog", "dialog_id": dialog_id})
        _recv(ws)  # dialog_active

        _send(
            ws, {"type": "teacher_message", "dialog_id": dialog_id, "text": "你说说看"}
        )

        c1 = _recv(ws)
        c2 = _recv(ws)
        end = _recv(ws)

    assert c1["type"] == "reply_chunk"
    assert c1["dialog_id"] == dialog_id
    assert c1["delta"] == "哦！"
    assert c1["chunk_seq"] == 0

    assert c2["type"] == "reply_chunk"
    assert c2["delta"] == "我懂了。"
    assert c2["chunk_seq"] == 1

    assert end["type"] == "reply_end"
    assert end["dialog_id"] == dialog_id
    assert end["full_content"] == "哦！我懂了。"
    assert end["self_resolved"] is True

    # 服务端 seq 单调递增（session_init=0, dialog_active=1, c1=2, c2=3, end=4）
    assert c1["seq"] == 2
    assert c2["seq"] == 3
    assert end["seq"] == 4


async def test_resolve_emits_dialog_resolved(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    dialog_id = next(iter(session.dialogs.keys()))
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)
        _send(ws, {"type": "select_dialog", "dialog_id": dialog_id})
        _recv(ws)
        _send(
            ws,
            {"type": "resolve", "dialog_id": dialog_id, "source": "self_resolve"},
        )
        msg = _recv(ws)

    assert msg["type"] == "dialog_resolved"
    assert msg["dialog_id"] == dialog_id
    assert msg["source"] == "self_resolve"
    assert session.get_dialog(dialog_id).status == "resolved"


async def test_abandon_emits_dialog_abandoned(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    dialog_id = next(iter(session.dialogs.keys()))
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)
        _send(ws, {"type": "abandon", "dialog_id": dialog_id})
        msg = _recv(ws)

    assert msg["type"] == "dialog_abandoned"
    assert msg["dialog_id"] == dialog_id
    assert session.get_dialog(dialog_id).status == "abandoned"


async def test_select_unknown_dialog_emits_error(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)
        _send(ws, {"type": "select_dialog", "dialog_id": "ghost-id"})
        err = _recv(ws)

    assert err["type"] == "error"
    assert err["code"] == "dialog_not_found"
    assert err["dialog_id"] == "ghost-id"


async def test_resolve_already_ended_emits_error(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    dialog_id = next(iter(session.dialogs.keys()))
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)
        _send(ws, {"type": "abandon", "dialog_id": dialog_id})
        _recv(ws)  # dialog_abandoned
        _send(ws, {"type": "resolve", "dialog_id": dialog_id})
        err = _recv(ws)

    assert err["type"] == "error"
    assert err["code"] in {"dialog_already_ended", "internal_error"}


async def test_unknown_session_id_closes_with_4004(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/qa-sessions/nonexistent") as ws:
            # 服务端会先发一条 session_not_found error 再关闭；试着收一下，然后下一次 recv 抛断开
            ws.receive_text()
            ws.receive_text()
    assert exc_info.value.code == 4004


async def test_invalid_json_emits_invalid_message_error(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)
        ws.send_text("not json at all")
        err = _recv(ws)

    assert err["type"] == "error"
    assert err["code"] == "invalid_message"


async def test_unknown_event_type_emits_invalid_message_error(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)
        _send(ws, {"type": "made_up_type"})
        err = _recv(ws)

    assert err["type"] == "error"
    assert err["code"] == "invalid_message"


async def test_second_connection_replaces_first(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    session = await _build_session(isolated_registry)
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws1:
        _recv(ws1)  # session_init on ws1
        with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws2:
            _recv(ws2)  # session_init on ws2
            # ws1 应当收到一帧 error{replaced} 然后被关闭
            replaced = _recv(ws1)
            assert replaced["type"] == "error"
            assert replaced["code"] == "replaced"


async def test_chunk_seq_resets_per_dialog(
    client: TestClient, isolated_registry: QASessionRegistry
) -> None:
    """跨 dialog 的 chunk_seq 计数器互不影响（每个 dialog 都从 0 起）。"""
    session = await _build_session(
        isolated_registry,
        scripted_streams=[
            # dialog 1
            [
                StudentStreamEvent(type="delta", delta="A"),
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(content="A", self_resolved=False, raw="A"),
                ),
            ],
            # dialog 2
            [
                StudentStreamEvent(type="delta", delta="B"),
                StudentStreamEvent(
                    type="final",
                    result=DialogReplyResult(content="B", self_resolved=False, raw="B"),
                ),
            ],
        ],
        student_count=2,
    )
    d1, d2 = list(session.dialogs.keys())
    with client.websocket_connect(f"/ws/qa-sessions/{session.id}") as ws:
        _recv(ws)  # session_init

        _send(ws, {"type": "select_dialog", "dialog_id": d1})
        _recv(ws)
        _send(ws, {"type": "teacher_message", "dialog_id": d1, "text": "T1"})
        chunk1 = _recv(ws)
        _recv(ws)  # reply_end

        _send(ws, {"type": "select_dialog", "dialog_id": d2})
        _recv(ws)
        _send(ws, {"type": "teacher_message", "dialog_id": d2, "text": "T2"})
        chunk2 = _recv(ws)

    assert chunk1["chunk_seq"] == 0
    assert chunk2["chunk_seq"] == 0
