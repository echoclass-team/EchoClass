"""1v1 答疑陪练 Mock WebSocket Server — 给 B 端前端开发用 (#71)。

启动一个独立 FastAPI 进程，**不调真实 LLM**，仅复用 ``api/qa_ws.py`` 的真实
endpoint 协议实现。学生回复用预设脚本逐 token 推送，模拟流式打字机效果。

启动方式::

    uv run python scripts/mock_ws_server.py
    # 默认监听 ws://localhost:8765/ws/qa-sessions/demo-session

启动时打印的 ``session_id`` 是固定的 ``demo-session``，B 端前端可直接连::

    const ws = new WebSocket("ws://localhost:8765/ws/qa-sessions/demo-session")

预置场景：

- 1 个教案（数学/分数初步）
- 2 个学生（小明 / 小红），各 1 个连续答疑 thread（共 2 个 dialog）
- 每个 dialog 的回复是带 100ms 间隔的 5-6 个 chunk，最后一条带 ``[懂了]``
- 同一 dialog 多轮发言会循环使用脚本（永远有回复）

> 与真实 endpoint 的差异：
> - 不需要 .env / API key
> - 学生 Agent 是 ``ScriptedFakeAgent``，``stream_in_dialog`` 直接 yield 预设 chunk
> - 注册路由完全相同（``/ws/qa-sessions/{session_id}``），协议帧 100% 一致
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.qa_ws import router as qa_ws_router
from schemas.dialog import DialogMessage, DialogReplyResult, StudentStreamEvent
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession
from services.qa_session_registry import get_registry

logger = logging.getLogger(__name__)


# ============================================================ Fake Agent


class _ScriptedPersona:
    def __init__(
        self,
        *,
        name: str,
        stage_id: str,
        subject_level: str,
        avatar_seed: str,
        summary: str,
    ) -> None:
        self.name = name
        self.stage_id = stage_id
        self.subject_level = subject_level
        self.avatar_seed = avatar_seed
        self.summary = summary


class ScriptedFakeAgent:
    """脚本驱动的 fake StudentAgent，可被 ``QASession`` 直接接管。

    ``stream_in_dialog`` 会逐 token 推送 ``CHUNK_SCRIPT``，每个 chunk 之间 sleep
    ``chunk_delay_seconds`` 模拟真实 LLM 流式速度。多轮调用循环复用脚本。
    """

    CHUNK_SCRIPT_NEUTRAL: list[str] = [
        "嗯……",
        "我觉得",
        "应该是",
        "下面那个数",
        "是表示",
        "分成几份吧？",
    ]
    CHUNK_SCRIPT_RESOLVED: list[str] = [
        "哦！",
        "我明白了——",
        "分母代表",
        "分成的份数，",
        "分子代表",
        "取了几份。",
        "[懂了]",
    ]

    def __init__(
        self,
        *,
        student_id: str,
        persona: _ScriptedPersona,
        questions: list[StudentQuestion],
        chunk_delay_seconds: float = 0.1,
    ) -> None:
        self.persona = persona
        self._student_id = student_id
        self._questions = questions
        self._chunk_delay = chunk_delay_seconds
        self._turn_count = 0

    async def generate_questions(
        self, lesson_meta: LessonMeta, *, count: int = 3
    ) -> list[StudentQuestion]:
        return self._questions[:count]

    async def stream_in_dialog(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history: list[DialogMessage] | None = None,
    ):
        """每 ``chunk_delay`` 秒 yield 一个 delta；每 3 轮触发一次 ``[懂了]``。"""
        self._turn_count += 1
        # 第 2 轮起按概率（实际是按轮数）触发"懂了"，让 B 端前端能调试 toast 流
        is_resolved_turn = self._turn_count % 3 == 0
        chunks = (
            self.CHUNK_SCRIPT_RESOLVED
            if is_resolved_turn
            else self.CHUNK_SCRIPT_NEUTRAL
        )

        accumulated = ""
        for piece in chunks:
            accumulated += piece
            # 推送 delta 时不包含 [懂了]（hold-back 模拟）
            visible = piece if piece != "[懂了]" else ""
            if visible:
                yield StudentStreamEvent(type="delta", delta=visible)
            await asyncio.sleep(self._chunk_delay)

        # 解析 [懂了]
        if accumulated.endswith("[懂了]"):
            content = accumulated[: -len("[懂了]")].rstrip()
            self_resolved = True
        else:
            content = accumulated
            self_resolved = False

        yield StudentStreamEvent(
            type="final",
            result=DialogReplyResult(
                content=content, self_resolved=self_resolved, raw=accumulated
            ),
        )


# ============================================================ 预置数据


def _demo_lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=["理解分数的含义", "学会读写分数"],
        key_points=["理解几分之一的含义", "分数的读写方法"],
        difficult_points=["分子分母的关系"],
    )


def _student_questions(student_id: str, name: str) -> list[StudentQuestion]:
    return [
        StudentQuestion(
            id=f"{student_id}-q0",
            speaker_id=student_id,
            speaker_name=name,
            content=f"老师，{name}想问：分数下面那个数是什么意思？",
            category="clarify_concept",
            difficulty="easy",
            linked_key_point="理解几分之一的含义",
            rationale="分子分母分不清。",
        )
    ]


async def _bootstrap_demo_session() -> str:
    """构造一个固定 id 的 demo session 并注册到全局 registry。"""
    registry = get_registry()

    session = QASession(lesson_meta=_demo_lesson(), session_id="demo-session")

    agent_a = ScriptedFakeAgent(
        student_id="ming",
        persona=_ScriptedPersona(
            name="小明",
            stage_id="p_middle",
            subject_level="中等",
            avatar_seed="ming",
            summary="活泼好动，爱抢答但容易跑题",
        ),
        questions=_student_questions("ming", "小明"),
    )
    agent_b = ScriptedFakeAgent(
        student_id="hong",
        persona=_ScriptedPersona(
            name="小红",
            stage_id="p_middle",
            subject_level="优秀",
            avatar_seed="hong",
            summary="文静内向，思考深入",
        ),
        questions=_student_questions("hong", "小红"),
    )

    await session.spawn([agent_a, agent_b], questions_per_student=2)
    await registry.register(session)
    return session.id


# ============================================================ FastAPI


def create_mock_app() -> FastAPI:
    """构造 mock FastAPI app — 仅注册 WS endpoint 与启动钩子。"""
    app = FastAPI(
        title="EchoClass Mock WS Server",
        description="给 B 端前端开发用的 mock，不调真实 LLM。",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(qa_ws_router)

    @app.on_event("startup")
    async def _startup() -> None:  # noqa: ANN101
        session_id = await _bootstrap_demo_session()
        logger.warning(
            "\n"
            "═══════════════════════════════════════════════════════════\n"
            "  EchoClass Mock WS Server is up\n"
            "  Demo session ready at:\n"
            "    ws://localhost:8765/ws/qa-sessions/%s\n"
            "  Students: 小明 / 小红 (各 1 个连续答疑 thread)\n"
            "  Resolved every 3rd turn (try 3+ rounds to trigger [懂了])\n"
            "═══════════════════════════════════════════════════════════\n",
            session_id,
        )

    @app.get("/health")
    async def _health() -> dict[str, Any]:
        registry = get_registry()
        return {"status": "ok", "sessions": await registry.list_ids()}

    return app


app = create_mock_app()


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "scripts.mock_ws_server:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
