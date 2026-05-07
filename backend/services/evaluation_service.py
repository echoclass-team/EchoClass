"""EvaluationService — 为一次 QASession 编排 Evaluator + Feedback。

职责
----
- 在 session 结束后串行运行 ``EvaluatorAgent`` → ``FeedbackAgent``
- 按 session_id 持有 ``asyncio.Lock``，保证同一 session 只触发一次
- 结果暂存进程内字典（``status`` + ``evaluation`` + ``feedback``），供 B3
  REST 拉取；DB 落盘（``evaluations`` / ``feedbacks`` 表）走 B 的 CRUD，当前
  PR 不直接写库，等 #M3-B3 完成后在 ``run`` 末尾再加一步即可。

契约
----
- ``schedule(session)``：fire-and-forget，同 session 重复调用只会跑一次
- ``run(session)``：阻塞版本，供测试和同步路径调用；内部同样走锁
- ``get(session_id)``：返回 bundle 或 ``None``
- LLM 失败时 evaluation.overall == ``"unavailable"``，feedback 返回
  ``[fallback]`` 占位（依 api_contract §2.6.4 降级语义）

非目标
------
- 不调度到其它 worker / 消息队列（M3 单进程足够）
- 不落盘（由 #M3-B3 接入后增补 CRUD 调用）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from agents.evaluator import EvaluatorAgent
from agents.feedback import FeedbackAgent
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from services.qa_session import QASession

logger = logging.getLogger(__name__)


BundleStatus = Literal["pending", "done", "failed"]


@dataclass
class EvaluationBundle:
    """某个 session 的评估 + 反馈结果聚合。"""

    status: BundleStatus
    evaluation: Optional[EvaluationReport] = None
    feedback: Optional[TeacherFeedback] = None
    error: Optional[str] = None


EvaluatorFactory = Callable[[], EvaluatorAgent]
FeedbackFactory = Callable[[], FeedbackAgent]


class EvaluationService:
    """进程内评估 + 反馈编排器。

    Parameters
    ----------
    evaluator_factory
        ``EvaluatorAgent`` 工厂；测试可注入 mock。默认无 LLM（走 mock 分）。
    feedback_factory
        ``FeedbackAgent`` 工厂；同上。
    """

    def __init__(
        self,
        evaluator_factory: EvaluatorFactory | None = None,
        feedback_factory: FeedbackFactory | None = None,
    ) -> None:
        self._evaluator_factory = evaluator_factory or EvaluatorAgent
        self._feedback_factory = feedback_factory or FeedbackAgent
        self._locks: dict[str, asyncio.Lock] = {}
        self._results: dict[str, EvaluationBundle] = {}
        self._global_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[EvaluationBundle]] = {}

    # --------------------------------------------------------------- public

    async def schedule(self, session: QASession) -> asyncio.Task[EvaluationBundle]:
        """Fire-and-forget 触发一次 evaluator + feedback。

        同 ``session.id`` 重复调用返回同一个 ``Task``，不会重复运行。
        """
        async with self._global_lock:
            existing = self._tasks.get(session.id)
            if existing is not None and not existing.done():
                return existing
            # 已完成的也直接返回旧 task（幂等），上层可按需 re-run 时先 clear
            if existing is not None and existing.done():
                return existing
            task = asyncio.create_task(self._run_locked(session))
            self._tasks[session.id] = task
            return task

    async def run(self, session: QASession) -> EvaluationBundle:
        """阻塞版本：直接等出结果。"""
        task = await self.schedule(session)
        return await task

    def get(self, session_id: str) -> EvaluationBundle | None:
        return self._results.get(session_id)

    async def clear(self) -> None:
        """仅测试用：清空锁与结果。"""
        async with self._global_lock:
            for task in self._tasks.values():
                if not task.done():
                    task.cancel()
            self._tasks.clear()
            self._locks.clear()
            self._results.clear()

    # -------------------------------------------------------------- internal

    async def _run_locked(self, session: QASession) -> EvaluationBundle:
        lock = self._locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            cached = self._results.get(session.id)
            if cached is not None and cached.status != "failed":
                return cached
            self._results[session.id] = EvaluationBundle(status="pending")
            bundle = await self._do_run(session)
            self._results[session.id] = bundle
            return bundle

    async def _do_run(self, session: QASession) -> EvaluationBundle:
        try:
            evaluator = self._evaluator_factory()
            evaluation = await evaluator.evaluate(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "EvaluationService evaluator failed for %s: %s",
                session.id,
                exc,
                exc_info=True,
            )
            evaluation = None

        try:
            feedback_agent = self._feedback_factory()
            feedback = await feedback_agent.generate(session, evaluation)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "EvaluationService feedback failed for %s: %s",
                session.id,
                exc,
                exc_info=True,
            )
            feedback = None

        if evaluation is None and feedback is None:
            return EvaluationBundle(
                status="failed",
                error="evaluator and feedback both failed",
            )

        logger.info(
            "EvaluationService ran for session %s (eval=%s, feedback=%s)",
            session.id,
            "ok" if evaluation else "missing",
            "ok" if feedback else "missing",
            extra={
                "event": "evaluation_service_run",
                "session_id": session.id,
                "evaluation_overall": (
                    evaluation.overall if evaluation is not None else None
                ),
                "feedback_tone": feedback.tone if feedback is not None else None,
            },
        )

        return EvaluationBundle(
            status="done",
            evaluation=evaluation,
            feedback=feedback,
        )


# 进程级单例
_default_service = EvaluationService()


def get_evaluation_service() -> EvaluationService:
    """返回进程级 ``EvaluationService`` 单例。"""
    return _default_service


__all__ = [
    "EvaluationBundle",
    "EvaluationService",
    "get_evaluation_service",
]
