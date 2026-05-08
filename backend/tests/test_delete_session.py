"""``DELETE /api/qa-sessions/{id}`` 路由测试 (#139 / 复盘 UI 删除入口)。

覆盖：

- 401：未登录
- 404：session 不存在
- 404：session 属于别的用户（不泄露存在性）
- 200：owner 删除成功，关联 dialog_messages / evaluations / feedbacks 全部清空
- 重复 DELETE 第二次返回 404
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.deps import CurrentUser, get_current_user
from db.crud import (
    save_dialog_message,
    save_qa_session,
    upsert_evaluation,
    upsert_feedback,
)
from db.models import (
    Base,
    DialogMessageRecord,
    EvaluationRecord,
    FeedbackRecord,
    Lesson,
    QASessionRecord,
)
from schemas.evaluation import EvaluationReport, RubricScore
from schemas.feedback import TeacherFeedback


_ALICE = CurrentUser(id="user-A", username="alice")
_BOB = CurrentUser(id="user-B", username="bob")
_SESSION_ID = "sess-del-001"
_LESSON_ID = "lesson-del-001"


# ============================================================ fixtures


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
def auth_as_alice() -> Iterator[None]:
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _ALICE
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def seed_alice_session(memory_db: sessionmaker) -> None:
    """在 DB 里写一条 alice 的完整 session（含消息 / 评估 / 反馈），供 DELETE 验证级联。"""
    db = memory_db()
    try:
        db.add(
            Lesson(
                id=_LESSON_ID,
                owner_id=_ALICE.id,
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
            lesson_id=_LESSON_ID,
            owner_id=_ALICE.id,
            persona_ids=["p1"],
        )
        # 2 条 dialog 消息
        save_dialog_message(
            db,
            session_id=_SESSION_ID,
            dialog_id="dialog-1",
            seq=1,
            role="teacher",
            content="老师的话",
        )
        save_dialog_message(
            db,
            session_id=_SESSION_ID,
            dialog_id="dialog-1",
            seq=2,
            role="student",
            content="学生回应",
        )
        # 评估 + 反馈
        upsert_evaluation(
            db,
            session_id=_SESSION_ID,
            rubric_version="v0",
            report_json=EvaluationReport(
                session_id=_SESSION_ID,
                rubric_version="v0",
                scores=[
                    RubricScore(
                        dimension="MR",
                        score=3,
                        rationale="r",
                        evidence=[],
                    )
                ],
                overall=3.0,
                generated_at=datetime.now(timezone.utc),
            ).model_dump_json(),
        )
        upsert_feedback(
            db,
            session_id=_SESSION_ID,
            feedback_json=TeacherFeedback(
                strengths=["s"],
                improvements=["i"],
                next_steps=["n"],
                tone="encouraging",
                generated_at=datetime.now(timezone.utc),
            ).model_dump_json(),
        )
    finally:
        db.close()


async def _delete(path: str) -> httpx.Response:
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.delete(path)


# ============================================================ 401


async def test_unauthenticated_delete_returns_401(memory_db) -> None:
    """无 Authorization → 401。"""
    resp = await _delete(f"/api/qa-sessions/{_SESSION_ID}")
    assert resp.status_code == 401


# ============================================================ 404


async def test_delete_returns_404_when_session_missing(
    memory_db, auth_as_alice
) -> None:
    resp = await _delete("/api/qa-sessions/no-such-session")
    assert resp.status_code == 404


async def test_delete_returns_404_when_session_belongs_to_other_user(
    memory_db, auth_as_alice
) -> None:
    """session 存在但 owner 不是当前用户 → 404，不泄露存在性。"""
    db = memory_db()
    try:
        db.add(
            Lesson(
                id="lesson-bob",
                owner_id=_BOB.id,
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
            owner_id=_BOB.id,
            persona_ids=[],
        )
    finally:
        db.close()

    resp = await _delete("/api/qa-sessions/sess-bob")
    assert resp.status_code == 404

    # bob 的 session 仍然在 DB，未被误删
    db = memory_db()
    try:
        assert (
            db.query(QASessionRecord).filter_by(id="sess-bob").count() == 1
        )
    finally:
        db.close()


# ============================================================ 200 cascade


async def test_delete_clears_session_and_related_rows(
    memory_db, auth_as_alice, seed_alice_session
) -> None:
    """owner DELETE 成功 → session + dialog_messages + evaluations + feedbacks 全部清空。"""
    # 前置：四张表都有 alice 的行
    db = memory_db()
    try:
        assert db.query(QASessionRecord).filter_by(id=_SESSION_ID).count() == 1
        assert (
            db.query(DialogMessageRecord).filter_by(session_id=_SESSION_ID).count()
            == 2
        )
        assert (
            db.query(EvaluationRecord).filter_by(session_id=_SESSION_ID).count() == 1
        )
        assert (
            db.query(FeedbackRecord).filter_by(session_id=_SESSION_ID).count() == 1
        )
    finally:
        db.close()

    resp = await _delete(f"/api/qa-sessions/{_SESSION_ID}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0

    # 后置：四张表的对应行全部清空（lesson 不删——lesson 是上传产物，不属于 session 生命周期）
    db = memory_db()
    try:
        assert db.query(QASessionRecord).filter_by(id=_SESSION_ID).count() == 0
        assert (
            db.query(DialogMessageRecord).filter_by(session_id=_SESSION_ID).count()
            == 0
        )
        assert (
            db.query(EvaluationRecord).filter_by(session_id=_SESSION_ID).count() == 0
        )
        assert (
            db.query(FeedbackRecord).filter_by(session_id=_SESSION_ID).count() == 0
        )
        # lesson 仍在
        assert db.query(Lesson).filter_by(id=_LESSON_ID).count() == 1
    finally:
        db.close()


async def test_delete_is_not_idempotent_returns_404_second_time(
    memory_db, auth_as_alice, seed_alice_session
) -> None:
    """第一次 DELETE 200，第二次 404（已被清掉）。"""
    first = await _delete(f"/api/qa-sessions/{_SESSION_ID}")
    assert first.status_code == 200

    second = await _delete(f"/api/qa-sessions/{_SESSION_ID}")
    assert second.status_code == 404
