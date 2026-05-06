"""用户表 SQLAlchemy 模型（M3 #B1 账号系统）。

设计：
- 与 KB 模块共享同一个 SQLite 数据库文件（echoclass.db）
- 使用独立的 Base，通过 Alembic env.py 统一管理 metadata
- 表名不加前缀，KB 表已有 ``kb_`` 前缀，不冲突
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


class Base(DeclarativeBase):
    """B 端模块统一的 declarative base。"""

    pass


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
