"""QA 答疑陪练 WebSocket endpoint。

路径: ``/ws/qa-sessions/{session_id}``

职责（与 ``backend/schemas/ws_events.py`` 协议规范严格对应）：

1. 连接建立后立即推送 ``session_init`` 帧（教案 + 学生列表 + 问题队列）
2. 解析客户端帧（discriminated union），分发到 ``QASession`` 对应方法
3. 把 ``QASession.stream_teacher_message`` 的流式事件 1:1 翻译为 ``reply_chunk`` /
   ``reply_end`` 服务端帧
4. 业务异常 → ``WsError`` 帧；同 session 新连接挤掉旧连接（``replaced``）

设计要点：

- **服务端帧序号 seq 单调递增**：每发一帧 seq+1，全连接共享一个计数器
- **chunk_seq 同 dialog 内单调**：流式回复时每次 ``WsReplyChunk`` 在该 dialog 内 +1
- **错误分类**：``dialog_not_found`` / ``dialog_already_ended`` / ``invalid_message``
  / ``internal_error`` / ``replaced``
- **业务调用串行化**：单 session 单连接 + 单协程读循环天然串行，不需要额外锁

A 端代写（领地 = B），合入 main 后 B 端可自由扩展新事件类型，但**协议变更需双 approve**。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from schemas.ws_events import (
    WsAbandon,
    WsClientEvent,
    WsDialogActive,
    WsDialogAbandoned,
    WsDialogResolved,
    WsError,
    WsErrorCode,
    WsReplyChunk,
    WsReplyEnd,
    WsResolve,
    WsSelectDialog,
    WsSessionInit,
    WsStudentInfo,
    WsTeacherMessage,
)
from services.qa_session import QASession, QASessionError
from services.qa_session_registry import QASessionRegistry, get_registry

logger = logging.getLogger(__name__)

router = APIRouter()

_client_adapter: TypeAdapter[WsClientEvent] = TypeAdapter(WsClientEvent)


# ============================================================ 单连接管理


class _ConnectionTracker:
    """同一 session_id 仅允许一个活动 WebSocket 连接。

    新连接到达时挤掉旧连接：旧连接收到 ``error{code:"replaced"}`` 后被关闭。
    """

    def __init__(self) -> None:
        self._active: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def take_over(
        self, session_id: str, new_ws: WebSocket
    ) -> Optional[WebSocket]:
        """把 ``new_ws`` 设为 session 的活动连接，返回被挤掉的旧连接（如有）。"""
        async with self._lock:
            old = self._active.get(session_id)
            self._active[session_id] = new_ws
            return old

    async def release(self, session_id: str, ws: WebSocket) -> None:
        """连接断开时调用：仅当当前活动连接确实是 ws 才移除。"""
        async with self._lock:
            if self._active.get(session_id) is ws:
                self._active.pop(session_id, None)


_tracker = _ConnectionTracker()


def get_tracker() -> _ConnectionTracker:
    """暴露给测试。"""
    return _tracker


# ============================================================ 帧发送辅助


class _SeqCounter:
    """连接级单调递增 seq 计数器。"""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


async def _send(ws: WebSocket, event: BaseModel) -> None:
    """把任一服务端 ``WsServerEvent`` 序列化为 JSON 并发出。"""
    await ws.send_text(event.model_dump_json())


async def _send_error(
    ws: WebSocket,
    seq: _SeqCounter,
    *,
    code: WsErrorCode,
    message: str,
    dialog_id: Optional[str] = None,
) -> None:
    try:
        await _send(
            ws,
            WsError(seq=seq.next(), code=code, message=message, dialog_id=dialog_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send error frame: %s / %s", code, message)


# ============================================================ 状态映射辅助


def _build_student_infos(session: QASession) -> list[WsStudentInfo]:
    """把 ``QASession._agents`` 里的 Persona 抽成轻量 ``WsStudentInfo`` 列表。

    顺序按学生在 spawn 时被注册的顺序（dict 维持插入顺序）。
    """
    infos: list[WsStudentInfo] = []
    for student_id, agent in session._agents.items():  # noqa: SLF001
        persona = agent.persona
        infos.append(
            WsStudentInfo(
                id=student_id,
                name=getattr(persona, "name", student_id),
                stage_id=getattr(persona, "stage_id", "") or "",
                subject_level=getattr(persona, "subject_level", "") or "",
                avatar_seed=getattr(persona, "avatar_seed", "") or "",
                summary=getattr(persona, "summary", "") or "",
            )
        )
    return infos


def _classify_dialog_error(session: QASession, dialog_id: str) -> WsErrorCode:
    """对 select / message / resolve / abandon 出错时分类错误码。"""
    if dialog_id not in session.dialogs:
        return "dialog_not_found"
    dialog = session.dialogs[dialog_id]
    if dialog.status in {"resolved", "abandoned"}:
        return "dialog_already_ended"
    return "internal_error"


# ============================================================ 事件分派


async def _dispatch(
    ws: WebSocket,
    session: QASession,
    event: WsClientEvent,
    seq: _SeqCounter,
    chunk_seq_state: dict[str, int],
) -> None:
    """根据客户端帧类型调用 ``QASession`` 并推送响应帧。"""
    if isinstance(event, WsSelectDialog):
        await _handle_select(ws, session, event, seq)
    elif isinstance(event, WsTeacherMessage):
        await _handle_message(ws, session, event, seq, chunk_seq_state)
    elif isinstance(event, WsResolve):
        await _handle_resolve(ws, session, event, seq)
    elif isinstance(event, WsAbandon):
        await _handle_abandon(ws, session, event, seq)
    else:  # pragma: no cover - 防御性
        await _send_error(ws, seq, code="invalid_message", message="unknown event type")


async def _handle_select(
    ws: WebSocket,
    session: QASession,
    event: WsSelectDialog,
    seq: _SeqCounter,
) -> None:
    if event.dialog_id not in session.dialogs:
        await _send_error(
            ws,
            seq,
            code="dialog_not_found",
            message=f"dialog {event.dialog_id} not found",
            dialog_id=event.dialog_id,
        )
        return
    dialog = session.dialogs[event.dialog_id]
    if dialog.status in {"resolved", "abandoned"}:
        await _send_error(
            ws,
            seq,
            code="dialog_already_ended",
            message=f"dialog {event.dialog_id} already ended (status={dialog.status})",
            dialog_id=event.dialog_id,
        )
        return
    try:
        session.start_dialog(event.dialog_id)
    except QASessionError as exc:
        await _send_error(
            ws,
            seq,
            code=_classify_dialog_error(session, event.dialog_id),
            message=str(exc),
            dialog_id=event.dialog_id,
        )
        return
    await _send(ws, WsDialogActive(seq=seq.next(), dialog_id=event.dialog_id))


async def _handle_message(
    ws: WebSocket,
    session: QASession,
    event: WsTeacherMessage,
    seq: _SeqCounter,
    chunk_seq_state: dict[str, int],
) -> None:
    if event.dialog_id not in session.dialogs:
        await _send_error(
            ws,
            seq,
            code="dialog_not_found",
            message=f"dialog {event.dialog_id} not found",
            dialog_id=event.dialog_id,
        )
        return
    dialog = session.dialogs[event.dialog_id]
    if dialog.status in {"resolved", "abandoned"}:
        await _send_error(
            ws,
            seq,
            code="dialog_already_ended",
            message=f"dialog {event.dialog_id} already ended (status={dialog.status})",
            dialog_id=event.dialog_id,
        )
        return

    chunk_seq = chunk_seq_state.get(event.dialog_id, 0)
    try:
        async for stream_evt in session.stream_teacher_message(
            event.dialog_id, event.text
        ):
            if stream_evt.type == "delta":
                if stream_evt.delta:
                    await _send(
                        ws,
                        WsReplyChunk(
                            seq=seq.next(),
                            dialog_id=event.dialog_id,
                            delta=stream_evt.delta,
                            chunk_seq=chunk_seq,
                        ),
                    )
                    chunk_seq += 1
            else:  # final
                if stream_evt.result is None:  # pragma: no cover - 防御
                    continue
                await _send(
                    ws,
                    WsReplyEnd(
                        seq=seq.next(),
                        dialog_id=event.dialog_id,
                        full_content=stream_evt.result.content,
                        self_resolved=stream_evt.result.self_resolved,
                    ),
                )
    except QASessionError as exc:
        await _send_error(
            ws,
            seq,
            code=_classify_dialog_error(session, event.dialog_id),
            message=str(exc),
            dialog_id=event.dialog_id,
        )
    except Exception as exc:  # noqa: BLE001 - LLM 上游错误等
        logger.exception(
            "stream_teacher_message failed for dialog %s: %s",
            event.dialog_id,
            exc,
        )
        await _send_error(
            ws,
            seq,
            code="llm_failed",
            message=f"upstream llm error: {exc!r}",
            dialog_id=event.dialog_id,
        )
    finally:
        chunk_seq_state[event.dialog_id] = chunk_seq


async def _handle_resolve(
    ws: WebSocket,
    session: QASession,
    event: WsResolve,
    seq: _SeqCounter,
) -> None:
    if event.dialog_id not in session.dialogs:
        await _send_error(
            ws,
            seq,
            code="dialog_not_found",
            message=f"dialog {event.dialog_id} not found",
            dialog_id=event.dialog_id,
        )
        return
    try:
        session.mark_resolved(event.dialog_id, source=event.source)
    except QASessionError as exc:
        await _send_error(
            ws,
            seq,
            code=_classify_dialog_error(session, event.dialog_id),
            message=str(exc),
            dialog_id=event.dialog_id,
        )
        return
    await _send(
        ws,
        WsDialogResolved(
            seq=seq.next(), dialog_id=event.dialog_id, source=event.source
        ),
    )


async def _handle_abandon(
    ws: WebSocket,
    session: QASession,
    event: WsAbandon,
    seq: _SeqCounter,
) -> None:
    if event.dialog_id not in session.dialogs:
        await _send_error(
            ws,
            seq,
            code="dialog_not_found",
            message=f"dialog {event.dialog_id} not found",
            dialog_id=event.dialog_id,
        )
        return
    session.abandon_dialog(event.dialog_id)  # 幂等
    await _send(
        ws,
        WsDialogAbandoned(seq=seq.next(), dialog_id=event.dialog_id),
    )


# ============================================================ endpoint


@router.websocket("/ws/qa-sessions/{session_id}")
async def qa_ws_endpoint(
    websocket: WebSocket,
    session_id: str,
    registry: QASessionRegistry = Depends(get_registry),  # noqa: B008
) -> None:
    """1v1 答疑陪练 WebSocket endpoint。

    协议详见 ``backend/schemas/ws_events.py`` / ``docs/api_contract.md §3``。

    依赖 ``get_registry`` 注入 ``QASessionRegistry``，测试可通过
    ``app.dependency_overrides[get_registry] = lambda: my_registry`` 替换。
    """
    await websocket.accept()

    session = await registry.get(session_id)
    if session is None:
        # 未注册的 session_id：用 1008 (policy violation) 关闭，前端按 4004 等价处理
        try:
            await _send(
                websocket,
                WsError(
                    seq=0,
                    code="session_not_found",
                    message=f"session {session_id} not registered",
                ),
            )
        except Exception:  # noqa: BLE001
            pass
        await websocket.close(code=4004)
        return

    # 挤掉旧连接
    seq = _SeqCounter()
    old_ws = await _tracker.take_over(session_id, websocket)
    if old_ws is not None:
        try:
            old_seq = _SeqCounter()  # 旧连接已经独立维护过 seq；这里只发一帧错误
            old_seq._n = 9_999_999  # 用一个明显大的 seq 表示"末班车"
            await _send(
                old_ws,
                WsError(
                    seq=old_seq.next(),
                    code="replaced",
                    message="connection replaced by a new one",
                ),
            )
            await old_ws.close(code=1000)
        except Exception:  # noqa: BLE001
            logger.debug("failed to close replaced ws cleanly", exc_info=True)

    chunk_seq_state: dict[str, int] = {}

    try:
        # 1. session_init
        await _send(
            websocket,
            WsSessionInit(
                seq=seq.next(),
                session_id=session.id,
                lesson=session.lesson_meta,
                students=_build_student_infos(session),
                questions=[d.question for d in session.dialogs.values()],
            ),
        )

        # 2. dispatch loop
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                client_event = _client_adapter.validate_json(raw)
            except ValidationError as exc:
                await _send_error(
                    websocket,
                    seq,
                    code="invalid_message",
                    message=f"invalid client frame: {exc.errors()[:1]}",
                )
                continue

            try:
                await _dispatch(websocket, session, client_event, seq, chunk_seq_state)
            except WebSocketDisconnect:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "qa_ws dispatch crashed for session %s: %s", session_id, exc
                )
                await _send_error(
                    websocket,
                    seq,
                    code="internal_error",
                    message=f"internal: {exc!r}",
                )
    finally:
        await _tracker.release(session_id, websocket)
