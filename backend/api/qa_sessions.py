"""QA 答疑陪练 REST 路由 (#B1 / Issue #72)。

本模块负责"拉起一个 QA session"、"查询 session 现状"、"显式结束 session"
三件事；session 内的多轮交互全部走 WebSocket（``api/qa_ws.py``）。

为什么 REST 而不是 WS 直接负责创建：
- 创建 session 涉及 ``StudentAgent.generate_questions`` 多次 LLM 调用，
  耗时几秒到十几秒，应该用一次性 HTTP 请求暴露明确成败语义
- 创建后再用 WS 连进去，前端能用 ``session_id`` 在多页面间复用 / 刷新
- summary 页查询场景天然适合幂等 GET，不应只能从 WS 拿

依赖注入：
- ``QASessionRegistry`` 走 ``get_registry``，与 WS endpoint 共享同一个进程级单例
- ``LessonLookup`` 走 ``get_lesson_lookup``，默认查 ``api.lessons._store``
- ``AgentFactory`` 走 ``get_agent_factory``，默认构造真实 ``StudentAgent``
  （含 ``LLMClient()``）。**测试可通过 dependency_overrides 注入 fake**，
  无需触网。

错误约定（与 ``api/response.py`` 全局 handler 配合）：
- 404 lesson_id 不存在 / session_id 不存在
- 400 persona_ids 空 / persona_id 找不到 / spawn 后无任何问题
- 500 内部异常（spawn 抛出 unexpected）
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException

from agents.student import StudentAgent
from api.lessons import get_lesson_record
from api.response import ok_response
from llm.client import LLMClient
from schemas.api import ApiResponse
from schemas.lesson import LessonRecord
from schemas.qa_session_api import (
    CreateQASessionData,
    CreateQASessionRequest,
    DialogStateSummary,
    QASessionEndData,
    QASessionStateData,
)
from schemas.stage import StageProfile, load_stage_profile_by_id
from schemas.student import Persona, load_personas
from schemas.ws_events import WsStudentInfo
from services.qa_session import QASession
from services.qa_session_registry import QASessionRegistry, get_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qa-sessions", tags=["qa-sessions"])


# ============================================================ DI 辅助


LessonLookup = Callable[[str], Optional[LessonRecord]]
"""``lesson_id -> LessonRecord | None``，便于测试替换。"""

AgentFactory = Callable[[Persona, Optional[StageProfile]], StudentAgent]
"""``(persona, stage) -> StudentAgent``，便于测试注入 fake。"""


def get_lesson_lookup() -> LessonLookup:
    """默认 lesson 查询器（M2 进程内字典；M3 切持久化时改这里）。"""
    return get_lesson_record


def _default_agent_factory(
    persona: Persona, stage: Optional[StageProfile]
) -> StudentAgent:
    return StudentAgent(llm=LLMClient(), persona=persona, stage=stage)


def get_agent_factory() -> AgentFactory:
    """默认 agent 工厂；测试通过 ``dependency_overrides`` 替换为 fake。"""
    return _default_agent_factory


# ============================================================ 内部辅助


def _build_student_info(persona: Persona) -> WsStudentInfo:
    """投影 Persona → WsStudentInfo（与 WS 首帧学生卡片同形）。"""
    return WsStudentInfo(
        id=persona.id or persona.name,
        name=persona.name,
        stage_id=persona.stage_id or "",
        subject_level=persona.effective_level or "",
        avatar_seed=persona.avatar_seed or "",
        summary=persona.summary or "",
    )


def _resolve_personas(persona_ids: list[str]) -> list[Persona]:
    """按 id 列表加载 personas。任意一项找不到 → 抛 400。

    保持入参顺序，便于前端预期与展示稳定。
    """
    if not persona_ids:
        raise HTTPException(status_code=400, detail="persona_ids must be non-empty")

    library = {p.id: p for p in load_personas() if p.id}
    # 兼容传 name 的早期前端：fallback 到 name 索引
    name_index = {p.name: p for p in load_personas()}

    resolved: list[Persona] = []
    missing: list[str] = []
    seen: set[str] = set()
    for pid in persona_ids:
        if pid in seen:
            # 去重而非报错：UI 误传重复 id 不应失败，但只算一份
            continue
        seen.add(pid)
        persona = library.get(pid) or name_index.get(pid)
        if persona is None:
            missing.append(pid)
            continue
        resolved.append(persona)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"persona_ids not found: {missing}",
        )
    return resolved


def _build_dialog_summary(dialog_id: str, session: QASession) -> DialogStateSummary:
    dialog = session.dialogs[dialog_id]
    preview = dialog.question.content[:80]
    return DialogStateSummary(
        id=dialog.id,
        student_id=dialog.student_id,
        student_name=dialog.question.speaker_name,
        status=dialog.status,
        question_preview=preview,
        turn_count=dialog.turn_count(),
        resolution_source=dialog.resolution_source,
    )


def _project_session_state(session: QASession) -> QASessionStateData:
    students: list[WsStudentInfo] = []
    for student_id, agent in session.iter_students():
        persona = agent.persona
        # 与 _build_student_info / WS 首帧保持一致：优先 effective_level
        level = (
            getattr(persona, "effective_level", None)
            or getattr(persona, "subject_level", "")
            or ""
        )
        students.append(
            WsStudentInfo(
                id=student_id,
                name=getattr(persona, "name", student_id),
                stage_id=getattr(persona, "stage_id", "") or "",
                subject_level=level,
                avatar_seed=getattr(persona, "avatar_seed", "") or "",
                summary=getattr(persona, "summary", "") or "",
            )
        )
    dialogs = [_build_dialog_summary(d.id, session) for d in session.dialogs.values()]
    counts: dict[str, int] = {
        "pending": 0,
        "active": 0,
        "resolved": 0,
        "abandoned": 0,
    }
    for d in session.dialogs.values():
        counts[d.status] = counts.get(d.status, 0) + 1
    return QASessionStateData(
        session_id=session.id,
        lesson=session.lesson_meta,
        students=students,
        dialogs=dialogs,
        pending=counts["pending"],
        active=counts["active"],
        resolved=counts["resolved"],
        abandoned=counts["abandoned"],
    )


# ============================================================ 路由


@router.post("", response_model=ApiResponse[CreateQASessionData])
async def create_qa_session(
    body: CreateQASessionRequest,
    registry: QASessionRegistry = Depends(get_registry),  # noqa: B008
    lesson_lookup: LessonLookup = Depends(get_lesson_lookup),  # noqa: B008
    agent_factory: AgentFactory = Depends(get_agent_factory),  # noqa: B008
) -> ApiResponse[CreateQASessionData]:
    """创建一个 1v1 答疑陪练 session。

    流程：
    1. 校验 ``lesson_id`` 存在（404 / 400）
    2. 解析 ``persona_ids`` → ``Persona`` 列表（400）
    3. 用 ``agent_factory`` 构造每个 ``StudentAgent``，按 persona.stage_id
       挂上 ``StageProfile``（找不到时为 None，``StudentAgent`` 会安全降级）
    4. 构造 ``QASession``，``await spawn(...)`` 并行让所有学生提问
    5. 注册到全局 registry，返回 session_id + WS URL + 首批问题
    """
    record = lesson_lookup(body.lesson_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"lesson_id {body.lesson_id!r} not found"
        )

    personas = _resolve_personas(body.persona_ids)

    agents: list[StudentAgent] = []
    for persona in personas:
        stage = load_stage_profile_by_id(persona.stage_id) if persona.stage_id else None
        try:
            agents.append(agent_factory(persona, stage))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "create_qa_session: agent_factory failed for persona %s: %s",
                persona.id or persona.name,
                exc,
            )
            raise HTTPException(
                status_code=500, detail=f"failed to build agent for {persona.name}"
            ) from exc

    session = QASession(lesson_meta=record.meta)
    try:
        questions = await session.spawn(
            agents, questions_per_student=body.count_per_student
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_qa_session: spawn failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"spawn failed: {exc!r}") from exc

    if not questions:
        raise HTTPException(
            status_code=500,
            detail="no questions generated; check student agents / LLM availability",
        )

    try:
        await registry.register(session)
    except ValueError as exc:
        # session_id 撞车（理论上几乎不可能：QASession 默认 uuid4）；500 即可
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    students = [_build_student_info(p) for p in personas]

    logger.info(
        "create_qa_session: %s lesson=%s personas=%d questions=%d",
        session.id,
        body.lesson_id,
        len(personas),
        len(questions),
    )

    return ok_response(
        CreateQASessionData(
            session_id=session.id,
            ws_url=f"/ws/qa-sessions/{session.id}",
            lesson=record.meta,
            students=students,
            questions=questions,
        )
    )


@router.get("/{session_id}", response_model=ApiResponse[QASessionStateData])
async def get_qa_session(
    session_id: str,
    registry: QASessionRegistry = Depends(get_registry),  # noqa: B008
) -> ApiResponse[QASessionStateData]:
    """查询 session 现状。WS 已断开 / 页面刷新场景使用。

    注：M2 进程内 registry，session 进程重启即丢；M3 持久化后会从 SQLite 兜底。
    """
    session = await registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return ok_response(_project_session_state(session))


@router.post("/{session_id}/end", response_model=ApiResponse[QASessionEndData])
async def end_qa_session(
    session_id: str,
    registry: QASessionRegistry = Depends(get_registry),  # noqa: B008
) -> ApiResponse[QASessionEndData]:
    """显式结束 session，返回 ``QASession.summary()``。

    幂等性：同 session_id 第二次调用返回 404（已不在 registry）。前端应
    在拿到第一次 summary 后跳转 summary 页，不应重复 end。

    注意：本接口**只**从 registry 移除并取 summary 快照；现存 WS 连接不会
    被服务器主动关闭（前端在 end 成功后应自行 ``client.close()``）。
    """
    session = await registry.pop(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    summary = session.summary()
    logger.info("end_qa_session: %s summary=%s", session_id, summary)
    return ok_response(QASessionEndData(session_id=session_id, summary=summary))
