"""B 端 SQLAlchemy 模型（M3 #B1 账号 + #B2 持久化）。

表：
- users: 用户表
- lessons: 教案持久化
- qa_sessions: 答疑会话
- dialog_messages: 对话消息落盘
- evaluations: 评估结果
- feedbacks: 反馈结果

设计：
- 与 KB 模块共享同一个 SQLite 数据库文件（echoclass.db）
- 使用独立的 Base，通过 Alembic env.py 统一管理 metadata
- 表名不加前缀，KB 表已有 ``kb_`` 前缀，不冲突
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


class Base(DeclarativeBase):
    """B 端模块统一的 declarative base。"""

    pass


# ============================================================ users


class User(Base):
    """用户表——M3 最小化：单租户 + username/password。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=_new_id
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ============================================================ lessons


class Lesson(Base):
    """教案持久化。content_hash 用于前端复用检测（同文件不重复解析）。"""

    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chroma_collection_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ============================================================ qa_sessions


class QASessionRecord(Base):
    """答疑会话持久化记录。"""

    __tablename__ = "qa_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("lessons.id"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), nullable=False, index=True
    )
    persona_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


# ============================================================ dialog_messages


class DialogMessageRecord(Base):
    """对话消息落盘。(session_id, seq) 唯一。"""

    __tablename__ = "dialog_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_dialog_msg_session_seq"),
        Index("ix_dialog_msg_session_dialog", "session_id", "dialog_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("qa_sessions.id"), nullable=False
    )
    dialog_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    self_resolved: Mapped[bool] = mapped_column(default=False)
    is_new_question: Mapped[bool] = mapped_column(default=False)
    question_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, default=None
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ============================================================ evaluations


class EvaluationRecord(Base):
    """评估结果（A 端写入，B 端只读展示）。"""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("qa_sessions.id"), unique=True, nullable=False
    )
    rubric_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    report_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ============================================================ feedbacks


class FeedbackRecord(Base):
    """反馈结果（A 端写入，B 端只读展示）。"""

    __tablename__ = "feedbacks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("qa_sessions.id"), unique=True, nullable=False
    )
    feedback_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
