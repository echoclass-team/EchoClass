"""KB 模块的 SQLAlchemy 引擎与 Session 工厂。

约定:

- 物理 DB 文件位于 ``data/echoclass.db``（仓库根 / data /，已 gitignored）
- 引擎是进程级单例，按需懒加载
- 提供 ``get_session()`` 上下文管理器供脚本与服务层使用
- 提供 ``create_all_tables()`` 直接建表（测试 / 第一次起库时用，正式迁移走 alembic）

环境变量:

- ``ECHOCLASS_DB_URL``: 覆盖默认 SQLite URL，用于测试（如 ``sqlite:///:memory:``）
  或将来切到 Postgres
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from kb.models import Base

logger = logging.getLogger(__name__)


# ============================================================ 路径与 URL


def _default_db_path() -> Path:
    """``<repo_root>/data/echoclass.db``。"""
    return Path(__file__).resolve().parent.parent.parent / "data" / "echoclass.db"


def get_db_url() -> str:
    """读取 ``ECHOCLASS_DB_URL`` 环境变量，否则用默认 SQLite 路径。"""
    if url := os.environ.get("ECHOCLASS_DB_URL"):
        return url
    db_path = _default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


# ============================================================ 引擎单例


_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _enable_sqlite_fk(dbapi_conn, _conn_record) -> None:
    """SQLite 默认不强制外键约束，每次连接进来要 PRAGMA 打开。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    """进程级懒加载引擎。"""
    global _engine, _SessionFactory
    if _engine is None:
        url = get_db_url()
        # SQLite 文件库需要 check_same_thread=False 才能跨线程使用
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        # ``:memory:`` 库必须用 StaticPool，否则不同 session 拿到独立的内存 DB
        # 导致跨 session 看不到对方的数据（测试常见踩坑点）
        kwargs: dict = {
            "echo": False,
            "connect_args": connect_args,
            "future": True,
        }
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _enable_sqlite_fk)
        _SessionFactory = sessionmaker(
            bind=_engine, autoflush=False, expire_on_commit=False, future=True
        )
        logger.debug("KB SQLAlchemy engine created: %s", url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionFactory is None:
        get_engine()  # 触发懒加载
    assert _SessionFactory is not None
    return _SessionFactory


@contextmanager
def get_session() -> Iterator[Session]:
    """常规上下文管理器：自动 commit / rollback / close。

    用法::

        from kb.database import get_session

        with get_session() as sess:
            theory = sess.get(Theory, "bandura_self_efficacy")
    """
    factory = get_session_factory()
    sess = factory()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


# ============================================================ Schema 管理


def create_all_tables(*, engine: Engine | None = None) -> None:
    """直接根据 ORM 元数据建表。

    本期 alembic 迁移作为正式路径；本函数主要用于：
    - 测试：``sqlite:///:memory:`` 起库
    - 第一次起仓库：``seed_edu_kb.py --create`` 时（避免必跑 alembic 提高 DX）
    """
    eng = engine or get_engine()
    Base.metadata.create_all(eng)
    logger.info("KB tables created (engine=%s)", eng.url)


def drop_all_tables(*, engine: Engine | None = None) -> None:
    """测试用：清空 KB 表（注意是真删！）。"""
    eng = engine or get_engine()
    Base.metadata.drop_all(eng)
    logger.warning("KB tables dropped (engine=%s)", eng.url)


def reset_engine_for_testing() -> None:
    """测试用：清掉单例，让下次 ``get_engine()`` 读新的环境变量。"""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
