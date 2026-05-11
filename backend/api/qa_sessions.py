"""QA 答疑陪练 REST 路由。

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

import json
import logging
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from api.deps import CurrentUser, get_current_user

from agents.student import StudentAgent
from api.lessons import get_lesson_record
from api.response import ok_response
from db.crud import (
    close_qa_session,
    delete_qa_session_record,
    get_dialog_messages,
    get_evaluation_by_session,
    get_feedback_by_session,
    get_qa_session_record,
    list_qa_sessions_by_owner,
    save_qa_session,
    upsert_evaluation,
    upsert_feedback,
)
from db.engine import SessionLocal
from llm.client import LLMClient
from schemas.api import ApiResponse
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta, LessonRecord
from schemas.qa_session_api import (
    CreateQASessionData,
    CreateQASessionRequest,
    DialogStateSummary,
    QASessionEndData,
    QASessionEvaluationData,
    QASessionStateData,
)
from services.evaluation_service import (
    EvaluationService,
    get_evaluation_service,
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
    """默认 lesson 查询器。"""
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
        history=list(dialog.messages),
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
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
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

    # DB 持久化
    db = SessionLocal()
    try:
        save_qa_session(
            db,
            session_id=session.id,
            lesson_id=body.lesson_id,
            owner_id=_user.id,
            persona_ids=body.persona_ids,
        )
    finally:
        db.close()

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
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
    registry: QASessionRegistry = Depends(get_registry),  # noqa: B008
) -> ApiResponse[QASessionStateData]:
    """查询 session 现状。WS 已断开 / 页面刷新场景使用。

    优先内存 registry；miss 时从 DB 重建只读视图。
    """
    session = await registry.get(session_id)
    if session is not None:
        return ok_response(_project_session_state(session))

    # DB fallback: 构建只读状态视图
    db = SessionLocal()
    try:
        record = get_qa_session_record(db, session_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"session {session_id!r} not found"
            )

        from schemas.dialog import DialogMessage as DMsg

        messages = get_dialog_messages(db, session_id)
        # 按 dialog_id 分组
        dialog_map: dict[str, list[DMsg]] = {}
        for m in messages:
            dialog_map.setdefault(m.dialog_id, []).append(
                DMsg(
                    role=m.role,
                    content=m.content,
                    timestamp=m.timestamp,
                    self_resolved=m.self_resolved,
                    is_new_question=m.is_new_question,
                    question_id=m.question_id,
                )
            )

        lesson_record = get_lesson_record(record.lesson_id)
        lesson_meta = (
            lesson_record.meta
            if lesson_record
            else LessonMeta(subject="", grade="", topic="unknown")
        )

        # persona id → name mapping (dialog_id == student_id == persona_id)
        from schemas.student import load_personas as _load_personas

        persona_name_map: dict[str, str] = {}
        try:
            for p in _load_personas():
                persona_name_map[p.id] = p.name
        except Exception:  # noqa: BLE001
            pass  # best-effort: fallback to dialog_id below

        dialogs: list[DialogStateSummary] = []
        for dialog_id, msgs in dialog_map.items():
            preview = msgs[0].content[:80] if msgs else ""
            student_name = persona_name_map.get(dialog_id, dialog_id)
            dialogs.append(
                DialogStateSummary(
                    id=dialog_id,
                    student_id=dialog_id,
                    student_name=student_name,
                    status="resolved",
                    question_preview=preview,
                    turn_count=(len(msgs) + 1) // 2,
                    resolution_source=None,
                    history=msgs,
                )
            )

        return ok_response(
            QASessionStateData(
                session_id=session_id,
                lesson=lesson_meta,
                students=[],
                dialogs=dialogs,
                pending=0,
                active=0,
                resolved=len(dialogs),
                abandoned=0,
            )
        )
    finally:
        db.close()


@router.get(
    "/{session_id}/evaluation",
    response_model=ApiResponse[QASessionEvaluationData],
)
async def get_qa_session_evaluation(
    session_id: str,
    response: Response,
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
    eval_service: EvaluationService = Depends(get_evaluation_service),  # noqa: B008
) -> ApiResponse[QASessionEvaluationData]:
    """读取某 session 的评估报告 + 师范生反馈。

    状态机：

    - 200 ``status="done"``：DB 命中 ``evaluations`` + ``feedbacks`` 行；
      或内存 ``EvaluationService`` 命中 done 且首次落盘成功。
    - 200 ``status="failed"``：内存命中 failed bundle；前端可显示 retry。
    - 202 ``status="pending"``：内存命中 pending bundle，或两边都 miss
      （此时评估尚未触发，前端轮询即可）。
    - 404：session 不存在或不属于当前用户（不区分两者，避免泄露存在性）。
    - 401：未登录（由 ``get_current_user`` 抛出）。
    """
    db = SessionLocal()
    try:
        record = get_qa_session_record(db, session_id)
        # 不存在 / 别人家的 session：统一 404，不泄露存在性
        if record is None or record.owner_id != _user.id:
            raise HTTPException(
                status_code=404, detail=f"session {session_id!r} not found"
            )

        # 优先读 DB 落盘（A 端写、B 端只读契约：models §evaluations/feedbacks）
        eval_row = get_evaluation_by_session(db, session_id)
        feedback_row = get_feedback_by_session(db, session_id)
        if eval_row is not None and feedback_row is not None:
            try:
                evaluation = EvaluationReport.model_validate_json(eval_row.report_json)
                feedback = TeacherFeedback.model_validate_json(
                    feedback_row.feedback_json
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "evaluation row corrupted for session %s, falling back to memory: %s",
                    session_id,
                    exc,
                )
            else:
                return ok_response(
                    QASessionEvaluationData(
                        status="done",
                        evaluation=evaluation,
                        feedback=feedback,
                    )
                )

        # DB miss：查内存 service（fallback；评估正在跑或刚跑完未落盘）
        bundle = eval_service.get(session_id)
        if bundle is None:
            response.status_code = 202
            return ok_response(QASessionEvaluationData(status="pending"))

        if bundle.status == "pending":
            response.status_code = 202
            return ok_response(QASessionEvaluationData(status="pending"))

        if bundle.status == "failed":
            return ok_response(
                QASessionEvaluationData(
                    status="failed",
                    error=bundle.error or "evaluation failed",
                )
            )

        # status == "done"：写穿到 DB 让下次直接命中
        if bundle.evaluation is not None:
            try:
                upsert_evaluation(
                    db,
                    session_id=session_id,
                    rubric_version=bundle.evaluation.rubric_version,
                    report_json=bundle.evaluation.model_dump_json(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("upsert_evaluation failed for %s: %s", session_id, exc)
        if bundle.feedback is not None:
            try:
                upsert_feedback(
                    db,
                    session_id=session_id,
                    feedback_json=bundle.feedback.model_dump_json(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("upsert_feedback failed for %s: %s", session_id, exc)

        return ok_response(
            QASessionEvaluationData(
                status="done",
                evaluation=bundle.evaluation,
                feedback=bundle.feedback,
            )
        )
    finally:
        db.close()


@router.post("/{session_id}/end", response_model=ApiResponse[QASessionEndData])
async def end_qa_session(
    session_id: str,
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
    registry: QASessionRegistry = Depends(get_registry),  # noqa: B008
    eval_service: EvaluationService = Depends(get_evaluation_service),  # noqa: B008
) -> ApiResponse[QASessionEndData]:
    """显式结束 session，返回 ``QASession.summary()``。

    幂等性：同 session_id 第二次调用返回 404（已不在 registry）。前端应
    在拿到第一次 summary 后跳转 summary 页，不应重复 end。

    副作用：
    - 关闭 DB session 状态（``close_qa_session``）
    - **fire-and-forget** 触发 ``EvaluationService.schedule(session)`` 启动
      Evaluator + Feedback。前端随后轮询 ``GET /{session_id}/evaluation``
      获取结果。

    注意：本接口**只**从 registry 移除并取 summary 快照；现存 WS 连接不会
    被服务器主动关闭（前端在 end 成功后应自行 ``client.close()``）。
    """
    session = await registry.pop(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    summary = session.summary()
    logger.info("end_qa_session: %s summary=%s", session_id, summary)

    # DB: 标记关闭
    db = SessionLocal()
    try:
        close_qa_session(db, session_id)
    finally:
        db.close()

    # 触发评估（fire-and-forget）：失败由 service 内部降级，不阻塞 end 响应
    try:
        await eval_service.schedule(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "end_qa_session: failed to schedule evaluation for %s: %s",
            session_id,
            exc,
        )

    return ok_response(QASessionEndData(session_id=session_id, summary=summary))


# ============================================================ 删除 session


@router.delete("/{session_id}", response_model=ApiResponse)
async def delete_qa_session(
    session_id: str,
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse:
    """删除一个 session 及其全部关联数据（dialog_messages / evaluations / feedbacks）。

    仅限 owner 删除。不存在或非 owner 返回 404。
    """
    db = SessionLocal()
    try:
        deleted = delete_qa_session_record(db, session_id, _user.id)
    finally:
        db.close()
    if not deleted:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    logger.info("delete_qa_session: %s by user %s", session_id, _user.id)
    return ok_response(None)


# ============================================================ 历史列表


class QASessionListItem(BaseModel):
    """GET /api/qa-sessions 历史列表单项。"""

    session_id: str
    lesson_id: str
    lesson_topic: str = ""
    status: str
    persona_ids: list[str] = Field(default_factory=list)
    created_at: str
    closed_at: Optional[str] = None


@router.get("", response_model=ApiResponse[list[QASessionListItem]])
async def list_qa_sessions(
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse[list[QASessionListItem]]:
    """GET /api/qa-sessions —— 返回当前用户的历史会话列表。"""
    db = SessionLocal()
    try:
        rows = list_qa_sessions_by_owner(db, _user.id)

        # batch-fetch lesson topics for display
        lesson_ids = list({r.lesson_id for r in rows})
        lesson_topics: dict[str, str] = {}
        if lesson_ids:
            from db.models import Lesson as LessonModel

            lesson_rows = (
                db.query(LessonModel.id, LessonModel.meta_json)
                .filter(LessonModel.id.in_(lesson_ids))
                .all()
            )
            for lid, meta_raw in lesson_rows:
                try:
                    meta = json.loads(meta_raw) if meta_raw else {}
                    lesson_topics[lid] = meta.get("topic", "")
                except Exception:  # noqa: BLE001
                    lesson_topics[lid] = ""
    finally:
        db.close()

    items = [
        QASessionListItem(
            session_id=r.id,
            lesson_id=r.lesson_id,
            lesson_topic=lesson_topics.get(r.lesson_id, ""),
            status=r.status,
            persona_ids=json.loads(r.persona_ids_json) if r.persona_ids_json else [],
            created_at=r.created_at.isoformat() if r.created_at else "",
            closed_at=r.closed_at.isoformat() if r.closed_at else None,
        )
        for r in rows
    ]
    return ok_response(items)
