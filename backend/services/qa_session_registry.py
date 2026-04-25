"""QASession 进程内注册表。

提供 ``QASession`` 实例的进程级单例存储，被 REST 路由（创建/查询/结束 session）
和 WebSocket endpoint（消费 session）共用。

设计取舍：

- **进程内字典 + asyncio.Lock**：M2 阶段单进程 / 单 worker，无需引入 Redis 等
  外部存储；后续要扩多进程再换实现
- **WeakValue 不用**：session 生命周期由业务显式控制（``register`` / ``unregister``），
  避免被 GC 突然回收
- **不与 SQLite 耦合**：M2 仅内存态；M3 持久化时这里加 ``load_from_db`` 即可

并发约定：

- ``register`` / ``unregister`` / ``get`` / ``pop`` 都是协程函数，内部用同一把锁
  保证字典操作原子；上层不需要再加锁
- ``QASession`` 实例本身**非线程安全**，调用方需保证对同一 session 串行操作
  （WebSocket endpoint 天然串行，所以没问题）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from services.qa_session import QASession

logger = logging.getLogger(__name__)


class QASessionRegistry:
    """进程内 ``QASession`` 字典封装。"""

    def __init__(self) -> None:
        self._sessions: dict[str, QASession] = {}
        self._lock = asyncio.Lock()

    async def register(self, session: QASession) -> None:
        """注册一个新 session。如同 id 已存在会抛 ``ValueError``。"""
        async with self._lock:
            if session.id in self._sessions:
                raise ValueError(f"session {session.id} already registered")
            self._sessions[session.id] = session
            logger.info(
                "QASessionRegistry: registered %s (total=%d)",
                session.id,
                len(self._sessions),
            )

    async def get(self, session_id: str) -> Optional[QASession]:
        """获取 session，不存在返回 None。"""
        async with self._lock:
            return self._sessions.get(session_id)

    async def pop(self, session_id: str) -> Optional[QASession]:
        """移除并返回 session；不存在返回 None。常用于显式结束 session。"""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                logger.info(
                    "QASessionRegistry: popped %s (remaining=%d)",
                    session_id,
                    len(self._sessions),
                )
            return session

    async def list_ids(self) -> list[str]:
        """列出当前注册的所有 session id。"""
        async with self._lock:
            return list(self._sessions.keys())

    async def clear(self) -> None:
        """清空注册表（仅测试用）。"""
        async with self._lock:
            self._sessions.clear()


# 进程级单例。生产代码与测试都通过 ``get_registry()`` 取用。
_default_registry = QASessionRegistry()


def get_registry() -> QASessionRegistry:
    """返回进程级 ``QASessionRegistry`` 单例。"""
    return _default_registry
