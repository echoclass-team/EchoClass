"""``scripts/mock_ws_server.py`` 的端到端验证 (#71)。

补全 #71 拆分清单第 4 步「e2e 验证」：``test_qa_ws.py`` 已用 fake agent
覆盖 endpoint 协议帧；本测试针对 **mock server 这个 B 端联调入口**
做完整启动 + 协议跑通验证，确保：

1. ``create_mock_app()`` 启动钩子能正确 bootstrap demo session
2. 协议帧（``session_init`` / ``reply_chunk`` / ``reply_end`` / ``dialog_resolved``）
   与 ``backend/schemas/ws_events.py`` 保持 1:1 一致
3. ScriptedFakeAgent 的 ``[懂了]`` 标记在 delta 中正确剥离
   （hold-back 模拟与真 StudentAgent 行为对齐）
4. seq / chunk_seq 单调递增不变量在 mock 路径同样成立

这部分挂在 mock 上的 e2e 不需要 .env / API key / LLM，CI 可反复跑。

测试写在 backend/tests/ 而非 backend/scripts/ 是因为 pytest 默认收集这里。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from api.qa_ws import get_tracker
from schemas.ws_events import (
    WsErrorCode,
    WsServerEvent,
)
from scripts.mock_ws_server import create_mock_app
from services.qa_session_registry import get_registry


_SERVER_EVENT_ADAPTER: TypeAdapter[WsServerEvent] = TypeAdapter(WsServerEvent)

SESSION_ID = "demo-session"
WS_PATH = f"/ws/qa-sessions/{SESSION_ID}"


# ============================================================ fixtures


@pytest.fixture
def mock_client():
    """启动 mock_ws_server 的真 FastAPI app，每个测试独立 lifespan。

    ``TestClient`` 的 ``with`` 会触发 ``startup`` 钩子，从而执行
    ``_bootstrap_demo_session()`` 把 ``demo-session`` 注册进 registry。
    测试结束时清理 registry + connection tracker，避免跨测试污染。
    """
    app = create_mock_app()
    with TestClient(app) as c:
        yield c
    # cleanup
    registry = get_registry()
    registry._sessions.clear()  # noqa: SLF001
    tracker = get_tracker()
    tracker._active.clear()  # noqa: SLF001


def _recv(ws) -> dict[str, Any]:
    return json.loads(ws.receive_text())


def _send(ws, payload: dict[str, Any]) -> None:
    ws.send_text(json.dumps(payload))


# ============================================================ tests


def test_mock_app_bootstraps_demo_session(mock_client: TestClient) -> None:
    """启动钩子应当把 ``demo-session`` 注册到全局 registry。"""
    registry = get_registry()
    assert SESSION_ID in registry._sessions  # noqa: SLF001


def test_mock_session_init_frame_matches_protocol(mock_client: TestClient) -> None:
    """连上 mock 立即收到的 ``session_init`` 应满足协议规范。"""
    with mock_client.websocket_connect(WS_PATH) as ws:
        frame = _recv(ws)

    # 通过 Pydantic 反序列化间接验证字段完整性 + Literal 受控枚举
    parsed = _SERVER_EVENT_ADAPTER.validate_python(frame)
    assert parsed.type == "session_init"
    assert parsed.session_id == SESSION_ID
    assert parsed.seq == 0
    # mock 预置: 1 个教案 + 2 个学生 + 4 个 dialog（每生 2 题）
    assert parsed.lesson.subject == "数学"
    assert {s.name for s in parsed.students} == {"小明", "小红"}
    assert len(parsed.questions) == 4


def test_mock_full_dialog_loop(mock_client: TestClient) -> None:
    """走完整一轮：select → teacher_message → reply_chunk*N → reply_end。

    断言以下不变量：
    - 全连接 ``seq`` 严格单调递增
    - 同 dialog 内 ``reply_chunk.chunk_seq`` 从 0 递增
    - delta 拼接结果 == ``reply_end.full_content``
    - ``[懂了]`` 标记不在任何 delta 中（hold-back 生效）
    """
    with mock_client.websocket_connect(WS_PATH) as ws:
        init = _recv(ws)
        first_dialog_id = init["questions"][0]["id"]

        _send(ws, {"type": "select_dialog", "dialog_id": first_dialog_id})
        active = _recv(ws)
        assert active["type"] == "dialog_active"
        assert active["dialog_id"] == first_dialog_id

        _send(
            ws,
            {
                "type": "teacher_message",
                "dialog_id": first_dialog_id,
                "text": "我们先看分数下面那个数。",
            },
        )

        chunks: list[str] = []
        chunk_seqs: list[int] = []
        seqs: list[int] = [init["seq"], active["seq"]]
        reply_end: dict[str, Any] | None = None

        while reply_end is None:
            frame = _recv(ws)
            seqs.append(frame["seq"])
            if frame["type"] == "reply_chunk":
                assert frame["dialog_id"] == first_dialog_id
                chunks.append(frame["delta"])
                chunk_seqs.append(frame["chunk_seq"])
                # 协议要求：delta 中不应出现 [懂了] 标记
                assert "[懂了]" not in frame["delta"]
            elif frame["type"] == "reply_end":
                reply_end = frame
            else:  # pragma: no cover - 出现意料之外帧时打印协助调试
                pytest.fail(f"unexpected frame type: {frame}")

    # 不变量验证
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
        f"seq 应严格单调递增，实际 {seqs}"
    )
    assert chunk_seqs == list(range(len(chunk_seqs))), (
        f"chunk_seq 应从 0 单调递增，实际 {chunk_seqs}"
    )
    assert "".join(chunks) == reply_end["full_content"], (
        "delta 拼接应等于 reply_end.full_content"
    )
    # mock 第 1 轮不触发 [懂了]（脚本里第 3 轮才触发）
    assert reply_end["self_resolved"] is False


def test_mock_resolve_emits_dialog_resolved(mock_client: TestClient) -> None:
    """``resolve`` 应回 ``dialog_resolved`` + 正确 source。"""
    with mock_client.websocket_connect(WS_PATH) as ws:
        init = _recv(ws)
        dialog_id = init["questions"][0]["id"]

        _send(
            ws,
            {
                "type": "resolve",
                "dialog_id": dialog_id,
                "source": "teacher_marked",
            },
        )
        frame = _recv(ws)

    assert frame["type"] == "dialog_resolved"
    assert frame["dialog_id"] == dialog_id
    assert frame["source"] == "teacher_marked"


def test_mock_replaced_on_second_connection(mock_client: TestClient) -> None:
    """同 session 第二个连接挤掉第一个；旧连接应收到 ``error{code:replaced}``。"""
    with mock_client.websocket_connect(WS_PATH) as ws_old:
        _ = _recv(ws_old)  # session_init
        with mock_client.websocket_connect(WS_PATH) as ws_new:
            _ = _recv(ws_new)  # 新连接也收到 session_init
            old_err = _recv(ws_old)

    assert old_err["type"] == "error"
    assert old_err["code"] == "replaced"
    # 受控枚举：协议规定的 7 个错误码之一
    assert old_err["code"] in WsErrorCode.__args__  # type: ignore[attr-defined]


def test_mock_health_endpoint(mock_client: TestClient) -> None:
    """mock server 仍然暴露 /health，方便 B 端启动确认。"""
    resp = mock_client.get("/health")
    assert resp.status_code == 200
