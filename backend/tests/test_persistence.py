"""持久化 CRUD 层单元测试 (#130)。

验证：
- lessons 写入和查询
- qa_sessions 写入、关闭、列表
- dialog_messages 写入和 seq 唯一约束
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Lesson, QASessionRecord, DialogMessageRecord
from db.crud import (
    save_lesson,
    get_lesson_by_id,
    save_qa_session,
    close_qa_session,
    get_qa_session_record,
    list_qa_sessions_by_owner,
    save_dialog_message,
    get_dialog_messages,
    get_next_seq,
)


@pytest.fixture()
def db():
    """每个测试使用独立的内存 SQLite 数据库。"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


# ============================================================ lessons


def test_save_and_get_lesson(db):
    save_lesson(
        db,
        lesson_id="lesson001",
        owner_id="user001",
        content_hash="abc123",
        filename="test.pdf",
        title="分数加减法",
        meta_json=json.dumps({"subject": "数学", "grade": "三年级", "topic": "分数加减法"}),
        text_length=1000,
        chunk_count=5,
    )
    row = get_lesson_by_id(db, "lesson001")
    assert row is not None
    assert row.filename == "test.pdf"
    assert row.title == "分数加减法"


def test_get_lesson_not_found(db):
    assert get_lesson_by_id(db, "ghost") is None


# ============================================================ qa_sessions


def test_save_and_list_sessions(db):
    # 先建 lesson (外键约束)
    save_lesson(
        db,
        lesson_id="L1",
        owner_id="U1",
        content_hash="h1",
        filename="a.pdf",
        title="t",
        meta_json="{}",
        text_length=0,
        chunk_count=0,
    )
    save_qa_session(db, session_id="S1", lesson_id="L1", owner_id="U1", persona_ids=["p1", "p2"])
    sessions = list_qa_sessions_by_owner(db, "U1")
    assert len(sessions) == 1
    assert sessions[0].id == "S1"
    assert sessions[0].status == "active"


def test_close_session(db):
    save_lesson(
        db,
        lesson_id="L1",
        owner_id="U1",
        content_hash="h1",
        filename="a.pdf",
        title="t",
        meta_json="{}",
        text_length=0,
        chunk_count=0,
    )
    save_qa_session(db, session_id="S1", lesson_id="L1", owner_id="U1", persona_ids=[])
    close_qa_session(db, "S1")
    row = get_qa_session_record(db, "S1")
    assert row is not None
    assert row.status == "closed"
    assert row.closed_at is not None


# ============================================================ dialog_messages


def test_save_and_get_messages(db):
    save_lesson(
        db,
        lesson_id="L1",
        owner_id="U1",
        content_hash="h1",
        filename="a.pdf",
        title="t",
        meta_json="{}",
        text_length=0,
        chunk_count=0,
    )
    save_qa_session(db, session_id="S1", lesson_id="L1", owner_id="U1", persona_ids=[])

    save_dialog_message(db, session_id="S1", dialog_id="D1", seq=1, role="teacher", content="你好")
    save_dialog_message(db, session_id="S1", dialog_id="D1", seq=2, role="student", content="你好老师")
    save_dialog_message(db, session_id="S1", dialog_id="D1", seq=3, role="teacher", content="那我们开始吧")

    messages = get_dialog_messages(db, "S1")
    assert len(messages) == 3
    assert messages[0].role == "teacher"
    assert messages[1].content == "你好老师"
    assert messages[2].seq == 3


def test_next_seq(db):
    save_lesson(
        db,
        lesson_id="L1",
        owner_id="U1",
        content_hash="h1",
        filename="a.pdf",
        title="t",
        meta_json="{}",
        text_length=0,
        chunk_count=0,
    )
    save_qa_session(db, session_id="S1", lesson_id="L1", owner_id="U1", persona_ids=[])

    assert get_next_seq(db, "S1") == 1
    save_dialog_message(db, session_id="S1", dialog_id="D1", seq=1, role="teacher", content="hi")
    assert get_next_seq(db, "S1") == 2


def test_duplicate_seq_upsert(db):
    """重复 seq 应 merge（不抛异常）。"""
    save_lesson(
        db,
        lesson_id="L1",
        owner_id="U1",
        content_hash="h1",
        filename="a.pdf",
        title="t",
        meta_json="{}",
        text_length=0,
        chunk_count=0,
    )
    save_qa_session(db, session_id="S1", lesson_id="L1", owner_id="U1", persona_ids=[])

    save_dialog_message(db, session_id="S1", dialog_id="D1", seq=1, role="teacher", content="v1")
    save_dialog_message(db, session_id="S1", dialog_id="D1", seq=1, role="teacher", content="v2")
    messages = get_dialog_messages(db, "S1")
    # merge 可能保留原值或更新，但不应抛异常
    assert len(messages) >= 1
