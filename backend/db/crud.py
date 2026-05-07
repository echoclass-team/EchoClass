"""持久化 CRUD 操作（M3 #B2）。

供 API 路由和 QASessionRegistry 调用，隔离 SQLAlchemy 细节。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from db.models import (
    DialogMessageRecord,
    Lesson,
    QASessionRecord,
)

logger = logging.getLogger(__name__)


# ============================================================ lessons


def save_lesson(
    db: Session,
    *,
    lesson_id: str,
    owner_id: str,
    content_hash: str,
    filename: str,
    title: str,
    meta_json: str,
    text_length: int,
    chunk_count: int,
) -> Lesson:
    row = Lesson(
        id=lesson_id,
        owner_id=owner_id,
        content_hash=content_hash,
        filename=filename,
        title=title,
        meta_json=meta_json,
        text_length=text_length,
        chunk_count=chunk_count,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_lesson_by_id(db: Session, lesson_id: str) -> Optional[Lesson]:
    return db.query(Lesson).filter(Lesson.id == lesson_id).first()


def delete_lesson(db: Session, lesson_id: str, owner_id: str) -> bool:
    """删除教案（仅限 owner）。返回是否确实删除了记录。"""
    row = (
        db.query(Lesson)
        .filter(Lesson.id == lesson_id, Lesson.owner_id == owner_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def list_lessons_by_owner(db: Session, owner_id: str) -> list[Lesson]:
    return (
        db.query(Lesson)
        .filter(Lesson.owner_id == owner_id)
        .order_by(Lesson.created_at.desc())
        .all()
    )


def get_lesson_by_hash(db: Session, content_hash: str, owner_id: str) -> Optional[Lesson]:
    return (
        db.query(Lesson)
        .filter(Lesson.content_hash == content_hash, Lesson.owner_id == owner_id)
        .first()
    )


# ============================================================ qa_sessions


def save_qa_session(
    db: Session,
    *,
    session_id: str,
    lesson_id: str,
    owner_id: str,
    persona_ids: list[str],
) -> QASessionRecord:
    row = QASessionRecord(
        id=session_id,
        lesson_id=lesson_id,
        owner_id=owner_id,
        persona_ids_json=json.dumps(persona_ids),
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def close_qa_session(db: Session, session_id: str) -> None:
    row = db.query(QASessionRecord).filter(QASessionRecord.id == session_id).first()
    if row:
        row.status = "closed"
        row.closed_at = datetime.now(timezone.utc)
        db.commit()


def get_qa_session_record(db: Session, session_id: str) -> Optional[QASessionRecord]:
    return db.query(QASessionRecord).filter(QASessionRecord.id == session_id).first()


def list_qa_sessions_by_owner(db: Session, owner_id: str) -> list[QASessionRecord]:
    return (
        db.query(QASessionRecord)
        .filter(QASessionRecord.owner_id == owner_id)
        .order_by(QASessionRecord.created_at.desc())
        .all()
    )


# ============================================================ dialog_messages


def save_dialog_message(
    db: Session,
    *,
    session_id: str,
    dialog_id: str,
    seq: int,
    role: str,
    content: str,
    self_resolved: bool = False,
    is_new_question: bool = False,
    question_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> DialogMessageRecord:
    # 唯一约束兜底：如已有相同 (session_id, seq) 则跳过
    existing = (
        db.query(DialogMessageRecord)
        .filter(
            DialogMessageRecord.session_id == session_id,
            DialogMessageRecord.seq == seq,
        )
        .first()
    )
    if existing:
        return existing
    row = DialogMessageRecord(
        session_id=session_id,
        dialog_id=dialog_id,
        seq=seq,
        role=role,
        content=content,
        self_resolved=self_resolved,
        is_new_question=is_new_question,
        question_id=question_id,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_dialog_messages(db: Session, session_id: str) -> list[DialogMessageRecord]:
    return (
        db.query(DialogMessageRecord)
        .filter(DialogMessageRecord.session_id == session_id)
        .order_by(DialogMessageRecord.seq)
        .all()
    )


def get_dialog_messages_for_dialog(
    db: Session, session_id: str, dialog_id: str
) -> list[DialogMessageRecord]:
    return (
        db.query(DialogMessageRecord)
        .filter(
            DialogMessageRecord.session_id == session_id,
            DialogMessageRecord.dialog_id == dialog_id,
        )
        .order_by(DialogMessageRecord.seq)
        .all()
    )


def get_next_seq(db: Session, session_id: str) -> int:
    """获取 session 下一条消息的 seq 号。"""
    from sqlalchemy import func

    result = (
        db.query(func.max(DialogMessageRecord.seq))
        .filter(DialogMessageRecord.session_id == session_id)
        .scalar()
    )
    return (result or 0) + 1
