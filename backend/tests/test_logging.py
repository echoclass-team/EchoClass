"""``utils.logging`` 单元测试 (#M3-A6 / #127)。

覆盖：

- ``JsonFormatter`` 输出字段完整性
- ``TextFormatter`` 带 context 的人读输出
- ``bind()`` 嵌套 / 退出自动恢复
- ``bind()`` 内嵌字段覆盖外层同名字段
- ``configure_logging`` 幂等（重复调用不累积 handler）
- JSON 输出可被 ``json.loads`` 解析
"""

from __future__ import annotations

import asyncio
import io
import json
import logging

import pytest

from utils.logging import (
    JsonFormatter,
    TextFormatter,
    bind,
    configure_logging,
    current_context,
    get_logger,
)


# ============================================================ bind


def test_bind_injects_fields_into_current_context() -> None:
    with bind(session_id="s1", dialog_id="d1"):
        ctx = current_context()
        assert ctx == {"session_id": "s1", "dialog_id": "d1"}
    # 退出后清空
    assert current_context() == {}


def test_bind_is_nestable_and_restores_outer() -> None:
    with bind(session_id="s1"):
        with bind(dialog_id="d1"):
            ctx = current_context()
            assert ctx == {"session_id": "s1", "dialog_id": "d1"}
        # 内层退出 → 只剩外层
        assert current_context() == {"session_id": "s1"}
    assert current_context() == {}


def test_bind_inner_overrides_outer_same_key() -> None:
    with bind(session_id="outer"):
        with bind(session_id="inner"):
            assert current_context()["session_id"] == "inner"
        # 内层退出恢复 outer
        assert current_context()["session_id"] == "outer"


def test_bind_isolated_across_asyncio_tasks() -> None:
    """不同 asyncio task 的 contextvar 天然隔离。"""
    results: list[dict] = []

    async def worker(tag: str) -> None:
        with bind(session_id=tag):
            await asyncio.sleep(0)  # 让其它 task 有机会交叉执行
            results.append(current_context())

    async def main() -> None:
        await asyncio.gather(worker("a"), worker("b"), worker("c"))

    asyncio.run(main())
    assert sorted(r["session_id"] for r in results) == ["a", "b", "c"]


# ============================================================ JsonFormatter


def _make_record(
    *,
    msg: str = "hello",
    level: int = logging.INFO,
    extra: dict | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return record


def test_json_formatter_emits_core_fields() -> None:
    fmt = JsonFormatter()
    record = _make_record(msg="plain")
    payload = json.loads(fmt.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["msg"] == "plain"
    # ts 是 ISO8601 带 Z 或 +00:00
    assert "ts" in payload and "T" in payload["ts"]


def test_json_formatter_includes_bind_context() -> None:
    fmt = JsonFormatter()
    with bind(session_id="s1", dialog_id="d1"):
        record = _make_record(msg="with-ctx")
        payload = json.loads(fmt.format(record))
    assert payload["session_id"] == "s1"
    assert payload["dialog_id"] == "d1"


def test_json_formatter_includes_extra_fields() -> None:
    fmt = JsonFormatter()
    record = _make_record(
        msg="evt",
        extra={"event": "llm_call", "token_in": 42, "token_out": 7},
    )
    payload = json.loads(fmt.format(record))
    assert payload["event"] == "llm_call"
    assert payload["token_in"] == 42
    assert payload["token_out"] == 7


def test_json_formatter_extra_overrides_bind_on_same_key() -> None:
    fmt = JsonFormatter()
    with bind(event="context-event"):
        record = _make_record(extra={"event": "explicit-event"})
        payload = json.loads(fmt.format(record))
    assert payload["event"] == "explicit-event"


def test_json_formatter_handles_exc_info() -> None:
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="oops", args=None, exc_info=sys.exc_info(),
        )
    payload = json.loads(fmt.format(record))
    assert "exc_info" in payload
    assert "ValueError: boom" in payload["exc_info"]


# ============================================================ TextFormatter


def test_text_formatter_appends_context_kv() -> None:
    fmt = TextFormatter()
    with bind(session_id="s1"):
        record = _make_record(msg="hi", extra={"event": "ping"})
        output = fmt.format(record)
    assert "hi" in output
    assert "session_id=s1" in output
    assert "event=ping" in output


def test_text_formatter_without_context_has_no_brackets() -> None:
    fmt = TextFormatter()
    record = _make_record(msg="bare")
    output = fmt.format(record)
    assert output.endswith("bare")


# ============================================================ configure_logging


def test_configure_logging_is_idempotent() -> None:
    root = logging.getLogger()
    initial = len(root.handlers)
    configure_logging()
    after_first = len(root.handlers)
    configure_logging()
    after_second = len(root.handlers)
    # 重复调用不累积
    assert after_first == after_second
    # 新增至多 1 个（可能首次调用已存在）
    assert after_first - initial <= 1


def test_configure_logging_json_emits_parseable_lines() -> None:
    buf = io.StringIO()
    configure_logging(fmt="json", stream=buf)
    logger = get_logger("test.json")
    with bind(session_id="s42"):
        logger.info("hello", extra={"event": "greet"})
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["session_id"] == "s42"
    assert payload["event"] == "greet"
    assert payload["logger"] == "test.json"


def test_configure_logging_text_falls_back_to_readable() -> None:
    buf = io.StringIO()
    configure_logging(fmt="text", stream=buf)
    logger = get_logger("test.text")
    with bind(session_id="sT"):
        logger.info("yo")
    line = buf.getvalue().strip().splitlines()[-1]
    # 不是 JSON
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)
    assert "yo" in line
    assert "session_id=sT" in line


# ============================================================ level


def test_configure_logging_respects_level() -> None:
    buf = io.StringIO()
    configure_logging(level="WARNING", fmt="json", stream=buf)
    logger = get_logger("test.level")
    logger.info("should-skip")
    logger.warning("should-show")
    lines = [ln for ln in buf.getvalue().strip().splitlines() if ln]
    assert any("should-show" in ln for ln in lines)
    assert not any("should-skip" in ln for ln in lines)
