"""``GET /api/qa-sessions/{id}/evaluation`` 路由测试 (#131 / M3-B3)。

覆盖状态机：

- 401：未登录（缺 Authorization header）
- 404：session 不存在 / session 不属于当前用户
- 202：DB 与内存均无评估记录；或内存命中 ``pending`` bundle
- 200 done：DB 命中 evaluations + feedbacks 行；或内存命中 ``done`` bundle 后落盘
- 200 failed：内存命中 ``failed`` bundle

测试用 mock EvaluatorAgent / FeedbackAgent fixture，不触网；DB 用临时 :memory:
SQLite，所有 CRUD 通过 monkeypatch ``db.engine.SessionLocal`` 走临时引擎。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.deps import CurrentUser, get_current_user
from db.crud import save_qa_session, upsert_evaluation, upsert_feedback
from db.models import Base
from schemas.evaluation import EvaluationReport, RubricScore
from schemas.feedback import TeacherFeedback
from services.evaluation_service import (
    EvaluationBundle,
    EvaluationService,
    get_evaluation_service,
)


_TEST_USER = CurrentUser(id="user-A", username="alice")
_OTHER_USER = CurrentUser(id="user-B", username="bob")
_SESSION_ID = "sess-eval-001"


# ============================================================ 共享 fixtures


@pytest.fixture()
def memory_db(monkeypatch) -> Iterator[sessionmaker]:
    """每个测试一个独立的 :memory: SQLite，monkeypatch 替换全局 SessionLocal。"""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr("db.engine.SessionLocal", Session)
    monkeypatch.setattr("api.qa_sessions.SessionLocal", Session)
    yield Session


@pytest.fixture()
def isolated_eval_service() -> Iterator[EvaluationService]:
    """每个测试单独一份 EvaluationService，避免跨用例污染缓存。"""
    from main import app

    service = EvaluationService()
    app.dependency_overrides[get_evaluation_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_evaluation_service, None)


@pytest.fixture()
def auth_as_alice() -> Iterator[None]:
    """以 user-A 身份发请求。"""
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def seed_session(memory_db: sessionmaker) -> None:
    """提前在 DB 写一条 user-A 的 QASessionRecord。"""
    db = memory_db()
    try:
        # 必须先建一条 lesson，否则 qa_sessions.lesson_id 外键失败
        from db.models import Lesson

        db.add(
            Lesson(
                id="lesson-001",
                owner_id=_TEST_USER.id,
                content_hash="x",
                filename="x.md",
                title="t",
                meta_json="{}",
            )
        )
        db.commit()
        save_qa_session(
            db,
            session_id=_SESSION_ID,
            lesson_id="lesson-001",
            owner_id=_TEST_USER.id,
            persona_ids=["p1"],
        )
    finally:
        db.close()


def _sample_report() -> EvaluationReport:
    return EvaluationReport(
        session_id=_SESSION_ID,
        rubric_version="v0",
        scores=[
            RubricScore(
                dimension="scaffolding",
                score=3,
                rationale="老师给出了 3 层脚手架",
                evidence=[],
            )
        ],
        overall=3.0,
        generated_at=datetime.now(timezone.utc),
    )


def _sample_feedback() -> TeacherFeedback:
    return TeacherFeedback(
        strengths=["提问引导清晰"],
        improvements=["可以多用反例"],
        next_steps=["梳理常见迷思"],
        tone="encouraging",
        generated_at=datetime.now(timezone.utc),
    )


async def _get(path: str, *, headers: dict | None = None) -> httpx.Response:
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


# ============================================================ 401


async def test_unauthenticated_request_returns_401() -> None:
    """无 token / 无依赖覆盖 → ``get_current_user`` 抛 401。"""
    # 没有 _auth_override 这个 fixture，且没传 Authorization
    resp = await _get(f"/api/qa-sessions/{_SESSION_ID}/evaluation")
    assert resp.status_code == 401


# ============================================================ 404


async def test_404_when_session_missing(
    memory_db, isolated_eval_service, auth_as_alice
) -> None:
    """session_id 不存在于 DB → 404。"""
    resp = await _get("/api/qa-sessions/no-such-session/evaluation")
    assert resp.status_code == 404


async def test_404_when_session_belongs_to_other_user(
    memory_db, isolated_eval_service, auth_as_alice
) -> None:
    """session 存在但 owner 不是当前用户 → 404（不泄露存在性）。"""
    db = memory_db()
    try:
        from db.models import Lesson

        db.add(
            Lesson(
                id="lesson-bob",
                owner_id=_OTHER_USER.id,
                content_hash="y",
                filename="y.md",
                title="t",
                meta_json="{}",
            )
        )
        db.commit()
        save_qa_session(
            db,
            session_id="sess-bob",
            lesson_id="lesson-bob",
            owner_id=_OTHER_USER.id,
            persona_ids=["p1"],
        )
    finally:
        db.close()

    resp = await _get("/api/qa-sessions/sess-bob/evaluation")
    assert resp.status_code == 404


# ============================================================ 202


async def test_202_when_no_evaluation_anywhere(
    memory_db, isolated_eval_service, auth_as_alice, seed_session
) -> None:
    """session 存在但 DB 与内存均无评估 → 202 pending。"""
    resp = await _get(f"/api/qa-sessions/{_SESSION_ID}/evaluation")
    assert resp.status_code == 202
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "pending"
    assert body["data"]["evaluation"] is None
    assert body["data"]["feedback"] is None


async def test_202_when_memory_bundle_pending(
    memory_db, isolated_eval_service, auth_as_alice, seed_session
) -> None:
    """内存 EvaluationService 命中 ``pending`` bundle → 202。"""
    isolated_eval_service._results[_SESSION_ID] = EvaluationBundle(status="pending")

    resp = await _get(f"/api/qa-sessions/{_SESSION_ID}/evaluation")
    assert resp.status_code == 202
    assert resp.json()["data"]["status"] == "pending"


# ============================================================ 200 done


async def test_200_when_db_has_both_rows(
    memory_db, isolated_eval_service, auth_as_alice, seed_session
) -> None:
    """DB 已落盘评估 + 反馈 → 直接 200 done，不查内存。"""
    db = memory_db()
    try:
        upsert_evaluation(
            db,
            session_id=_SESSION_ID,
            rubric_version="v0",
            report_json=_sample_report().model_dump_json(),
        )
        upsert_feedback(
            db,
            session_id=_SESSION_ID,
            feedback_json=_sample_feedback().model_dump_json(),
        )
    finally:
        db.close()

    resp = await _get(f"/api/qa-sessions/{_SESSION_ID}/evaluation")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "done"
    assert data["evaluation"]["session_id"] == _SESSION_ID
    assert data["evaluation"]["scores"][0]["dimension"] == "scaffolding"
    assert data["feedback"]["tone"] == "encouraging"
    assert data["feedback"]["strengths"] == ["提问引导清晰"]


async def test_200_done_falls_back_to_memory_and_persists(
    memory_db, isolated_eval_service, auth_as_alice, seed_session
) -> None:
    """DB miss + 内存 done bundle → 返回 200 done 并写穿 DB（下次直接命中）。"""
    isolated_eval_service._results[_SESSION_ID] = EvaluationBundle(
        status="done",
        evaluation=_sample_report(),
        feedback=_sample_feedback(),
    )

    resp = await _get(f"/api/qa-sessions/{_SESSION_ID}/evaluation")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "done"
    assert data["evaluation"]["overall"] == 3.0

    # 验证已落盘：直接查 DB
    from db.crud import get_evaluation_by_session, get_feedback_by_session

    db = memory_db()
    try:
        assert get_evaluation_by_session(db, _SESSION_ID) is not None
        assert get_feedback_by_session(db, _SESSION_ID) is not None
    finally:
        db.close()


# ============================================================ 200 failed


async def test_200_failed_when_memory_bundle_failed(
    memory_db, isolated_eval_service, auth_as_alice, seed_session
) -> None:
    """内存命中 ``failed`` bundle → 200 + status=failed + error 文案。"""
    isolated_eval_service._results[_SESSION_ID] = EvaluationBundle(
        status="failed",
        error="evaluator crashed",
    )

    resp = await _get(f"/api/qa-sessions/{_SESSION_ID}/evaluation")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "failed"
    assert data["error"] == "evaluator crashed"
    assert data["evaluation"] is None
    assert data["feedback"] is None
