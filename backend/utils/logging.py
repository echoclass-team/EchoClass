"""结构化 JSON 日志 (#M3-A6 / issue #127)。

设计目标
--------

- **最小侵入**：已有 ``logger = logging.getLogger(__name__)`` 调用无需改动，
  通过配置 root logger 的 handler + formatter 统一输出格式
- **字段可追踪**：关键字段 ``session_id`` / ``dialog_id`` / ``user_id`` / ``event``
  等通过 ``bind(...)`` 注入 ``contextvars``，在当前异步上下文内所有日志自动带上
- **双模式**：``LOG_FORMAT=json``（默认，生产 / CI）vs ``LOG_FORMAT=text``（人读）
- **零新依赖**：只用 stdlib ``logging`` + ``contextvars``

典型用法
--------

启动时配置一次::

    # backend/main.py
    from utils.logging import configure_logging
    configure_logging()

业务代码里绑定上下文 + 打显式事件::

    from utils.logging import bind, get_logger

    logger = get_logger(__name__)

    with bind(session_id=session.id, dialog_id=dialog_id):
        logger.info("teacher_message_received", extra={"event": "teacher_message"})
        # 此 with 块内所有 logger 调用都会自动带上 session_id / dialog_id

``extra={"event": "..."}`` 是约定的事件类型字段，方便日志聚合检索（如
``jq 'select(.event == "llm_call")'``）。
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

# ============================================================ 上下文存储

# 当前异步任务的结构化日志上下文。每次 bind() 会把新字段合并进去，
# 退出 with 块时自动恢复。内容是 dict[str, Any]，键为日志字段名。
_log_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "echoclass_log_context", default={}
)

# 约定的保留字段；业务调用 bind() 时传入的 key 不会与 LogRecord 内置字段冲突。
# 这里只列出本项目显式关心的字段，其它自定义 key 也可以传入。
_KNOWN_CONTEXT_KEYS = (
    "session_id",
    "dialog_id",
    "user_id",
    "agent",
    "event",
    "lesson_id",
)


def current_context() -> dict[str, Any]:
    """返回当前生效的日志上下文快照（只读视图）。主要给测试使用。"""
    return dict(_log_context.get())


@contextmanager
def bind(**fields: Any) -> Iterator[None]:
    """把 ``fields`` 合并进当前异步上下文的日志字段，with 退出时自动回滚。

    可嵌套：内层 bind 会覆盖同名外层字段，退出内层后恢复外层值。

    示例::

        with bind(session_id="s1"):
            logger.info("a")                 # 带 session_id=s1
            with bind(dialog_id="d1"):
                logger.info("b")             # 带 session_id=s1, dialog_id=d1
            logger.info("c")                 # 只带 session_id=s1
    """
    current = _log_context.get()
    merged = {**current, **fields}
    token = _log_context.set(merged)
    try:
        yield
    finally:
        _log_context.reset(token)


# ============================================================ Formatter

# LogRecord 内置属性；我们在 JSON 输出时需要显式挑选业务关心的字段，
# 避免把 pathname / lineno 等噪音全写进去。
_STANDARD_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    """把 ``LogRecord`` 格式化为单行 JSON。

    输出字段：

    - ``ts``：ISO8601 UTC 时间戳
    - ``level``：日志等级（INFO / WARNING / ...）
    - ``logger``：logger 名（通常是模块 ``__name__``）
    - ``msg``：渲染后的消息文本
    - ``event``：事件类型（来自 ``extra={"event": "..."}`` 或当前 bind 上下文）
    - 当前 ``bind()`` 上下文中的所有字段（session_id / dialog_id / ...）
    - 调用方通过 ``extra=`` 传入的任意自定义字段
    - ``exc_info``：异常 traceback（如有）
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # 当前异步上下文的 bind 字段
        ctx = _log_context.get()
        for key, value in ctx.items():
            payload.setdefault(key, value)

        # 调用方 extra={} 传入的非标准字段（优先级高于 bind 上下文）
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=_json_default)


class TextFormatter(logging.Formatter):
    """人读格式：``HH:MM:SS LEVEL logger [k=v ...] msg``。本地开发用。"""

    default_fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.default_fmt, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        ctx = _log_context.get()
        extras: dict[str, Any] = {}
        for key, value in ctx.items():
            extras.setdefault(key, value)
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS:
                continue
            extras[key] = value
        if not extras:
            return base
        tail = " ".join(f"{k}={v}" for k, v in extras.items())
        return f"{base} [{tail}]"


def _json_default(obj: Any) -> Any:
    """JSON fallback：datetime / set / Pydantic BaseModel 等友好转换。"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    # Pydantic v2 BaseModel
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:  # noqa: BLE001
            pass
    return str(obj)


# ============================================================ 入口 API


def configure_logging(
    *, level: str | None = None, fmt: str | None = None, stream: Any = None
) -> None:
    """配置 root logger。应用启动时调用一次即可。

    Parameters
    ----------
    level:
        日志等级，默认读 ``LOG_LEVEL`` 环境变量，fallback 到 ``INFO``。
    fmt:
        输出格式：``"json"`` 或 ``"text"``。默认读 ``LOG_FORMAT`` 环境变量，
        fallback 到 ``"json"``。
    stream:
        输出流，默认 stderr（与 ``StreamHandler`` 默认一致）。测试时可传
        ``io.StringIO()`` 捕获输出。

    本函数是幂等的：重复调用会先移除已安装的 EchoClass handler 再重新安装，
    不会累积多份 handler。
    """
    resolved_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    resolved_fmt = (fmt or os.getenv("LOG_FORMAT") or "json").lower()

    formatter: logging.Formatter
    if resolved_fmt == "text":
        formatter = TextFormatter()
    else:
        formatter = JsonFormatter()

    handler = logging.StreamHandler(stream) if stream is not None else logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.set_name("echoclass")

    root = logging.getLogger()
    # 移除同名旧 handler（幂等）
    for existing in list(root.handlers):
        if getattr(existing, "name", None) == "echoclass":
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved_level)


def get_logger(name: str) -> logging.Logger:
    """薄封装，保持调用点与 stdlib 习惯一致。

    目前就是 ``logging.getLogger(name)``；若将来切换实现（如 structlog）也只改这里。
    """
    return logging.getLogger(name)


__all__ = [
    "bind",
    "configure_logging",
    "current_context",
    "get_logger",
    "JsonFormatter",
    "TextFormatter",
]
