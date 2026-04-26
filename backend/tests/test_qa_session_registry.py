"""``QASessionRegistry`` 单元测试 (#71)。"""

from __future__ import annotations

import pytest

from schemas.lesson import LessonMeta
from services.qa_session import QASession
from services.qa_session_registry import QASessionRegistry, get_registry


def _session(session_id: str) -> QASession:
    return QASession(
        lesson_meta=LessonMeta(
            subject="数学", grade="三年级", topic="分数"
        ),
        session_id=session_id,
    )


async def test_register_and_get_roundtrip() -> None:
    reg = QASessionRegistry()
    s = _session("s1")
    await reg.register(s)
    got = await reg.get("s1")
    assert got is s


async def test_get_unknown_returns_none() -> None:
    reg = QASessionRegistry()
    assert await reg.get("ghost") is None


async def test_pop_removes_and_returns() -> None:
    reg = QASessionRegistry()
    s = _session("s1")
    await reg.register(s)
    popped = await reg.pop("s1")
    assert popped is s
    assert await reg.get("s1") is None


async def test_pop_unknown_returns_none() -> None:
    reg = QASessionRegistry()
    assert await reg.pop("ghost") is None


async def test_register_duplicate_raises() -> None:
    reg = QASessionRegistry()
    s = _session("s1")
    await reg.register(s)
    with pytest.raises(ValueError):
        await reg.register(s)


async def test_list_ids_returns_all_registered() -> None:
    reg = QASessionRegistry()
    await reg.register(_session("a"))
    await reg.register(_session("b"))
    ids = await reg.list_ids()
    assert set(ids) == {"a", "b"}


async def test_clear_empties_registry() -> None:
    reg = QASessionRegistry()
    await reg.register(_session("a"))
    await reg.clear()
    assert await reg.list_ids() == []


def test_get_registry_returns_module_singleton() -> None:
    a = get_registry()
    b = get_registry()
    assert a is b
