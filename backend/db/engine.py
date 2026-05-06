"""SQLAlchemy engine + session 工厂（M3 #B1）。

单例 engine，所有模块共用。URL 优先级：
1. ``ECHOCLASS_DB_URL`` 环境变量
2. 默认 ``sqlite:///data/echoclass.db``（项目根目录下）
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "echoclass.db"
_DEFAULT_URL = f"sqlite:///{_DEFAULT_DB_PATH}"

DATABASE_URL = os.environ.get("ECHOCLASS_DB_URL", _DEFAULT_URL)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 需要
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Session:  # type: ignore[misc]
    """FastAPI Depends 用的 DB session 生成器。"""
    db = SessionLocal()
    try:
        yield db  # type: ignore[misc]
    finally:
        db.close()
