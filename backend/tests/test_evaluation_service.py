"""``services.evaluation_service`` 单元测试 (#M3-A3 / #M3-A4)。

覆盖：
- schedule 触发 evaluator + feedback，并把结果存入内存字典
- 同 session 并发 schedule 只运行一次
- evaluator 失败时仍产出 feedback（降级）
- evaluator 返回 overall=unavailable 时，真实 feedback 路径短路走 fallback
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from agents.evaluator import EvaluatorAgent
from agents.feedback import FeedbackAgent
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta
from services.evaluation_service import EvaluationService
from services.qa_session import QASession


# ============================================================ helpers


def _fake_session(session_id: str = "sess-svc") -> QASession:
    lesson = LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=["理解分数含义"],
        key_points=["分数的定义"],
        difficult_points=["平均分的理解"],
    )
    return QASession(lesson_meta=lesson, session_id=session_id)


class _CountingEvaluator:
    """最小 evaluator：直接返回一份固定报告，并记录调用次数。"""

    def __init__(self, *, fail: bool = False, overall: Any = 3.0) -> None:
        self.calls = 0
        self._fail = fail
        self._overall = overall

    async def evaluate(self, session: QASession) -> EvaluationReport:
        self.calls += 1
        if self._fail:
            raise RuntimeError("boom")
        return EvaluationReport(
            session_id=session.id,
            rubric_version="v0",
            scores=[],
            overall=self._overall,
            generated_at=datetime.now(timezone.utc),
        )


class _CountingFeedback:
    def __init__(self) -> None:
        self.calls = 0
        self.last_evaluation: EvaluationReport | None = None

    async def generate(
        self,
        session: QASession,
        evaluation: EvaluationReport | None = None,
    ) -> TeacherFeedback:
        self.calls += 1
        self.last_evaluation = evaluation
        return TeacherFeedback(
            strengths=["s"],
            improvements=["i"],
            next_steps=["n"],
            tone="encouraging",
            generated_at=datetime.now(timezone.utc),
        )


# ============================================================ schedule / run


async def test_run_produces_bundle_and_stores_in_memory() -> None:
    evaluator = _CountingEvaluator()
    feedback = _CountingFeedback()
    svc = EvaluationService(
        evaluator_factory=lambda: evaluator,  # type: ignore[arg-type]
        feedback_factory=lambda: feedback,  # type: ignore[arg-type]
    )
    session = _fake_session()

    bundle = await svc.run(session)

    assert bundle.status == "done"
    assert bundle.evaluation is not None
    assert bundle.feedback is not None
    assert svc.get(session.id) is bundle
    assert feedback.last_evaluation is bundle.evaluation


async def test_concurrent_schedule_runs_only_once() -> None:
    evaluator = _CountingEvaluator()
    feedback = _CountingFeedback()
    svc = EvaluationService(
        evaluator_factory=lambda: evaluator,  # type: ignore[arg-type]
        feedback_factory=lambda: feedback,  # type: ignore[arg-type]
    )
    session = _fake_session()

    tasks = [await svc.schedule(session) for _ in range(5)]
    results = await asyncio.gather(*tasks)

    assert all(r.status == "done" for r in results)
    assert all(r is results[0] for r in results)
    assert evaluator.calls == 1
    assert feedback.calls == 1


async def test_schedule_after_done_is_idempotent() -> None:
    evaluator = _CountingEvaluator()
    feedback = _CountingFeedback()
    svc = EvaluationService(
        evaluator_factory=lambda: evaluator,  # type: ignore[arg-type]
        feedback_factory=lambda: feedback,  # type: ignore[arg-type]
    )
    session = _fake_session()

    first = await svc.run(session)
    second = await svc.run(session)

    assert first is second
    assert evaluator.calls == 1
    assert feedback.calls == 1


async def test_evaluator_failure_still_produces_feedback() -> None:
    evaluator = _CountingEvaluator(fail=True)
    feedback = _CountingFeedback()
    svc = EvaluationService(
        evaluator_factory=lambda: evaluator,  # type: ignore[arg-type]
        feedback_factory=lambda: feedback,  # type: ignore[arg-type]
    )
    session = _fake_session()

    bundle = await svc.run(session)

    assert bundle.status == "done"
    assert bundle.evaluation is None
    assert bundle.feedback is not None
    assert feedback.last_evaluation is None


async def test_clear_resets_state() -> None:
    evaluator = _CountingEvaluator()
    feedback = _CountingFeedback()
    svc = EvaluationService(
        evaluator_factory=lambda: evaluator,  # type: ignore[arg-type]
        feedback_factory=lambda: feedback,  # type: ignore[arg-type]
    )
    session = _fake_session()
    await svc.run(session)
    assert svc.get(session.id) is not None

    await svc.clear()

    assert svc.get(session.id) is None
    await svc.run(session)
    assert evaluator.calls == 2


# ============================================================ default factories


async def test_default_factories_inject_llm_client(monkeypatch: Any) -> None:
    """未注入 factory 时使用默认 ``EvaluatorAgent`` / ``FeedbackAgent`` 走真实 LLM 路径。

    无 ``OPENAI_API_KEY`` 时 LLMClient 在调用现场抛 ValueError，被 agent 内部
    捕获后降级：evaluation.overall == "unavailable"，feedback 走 fallback 占位。
    本用例不联网，断言降级路径符合 §2.6.4 契约。
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    svc = EvaluationService()
    evaluator = svc._evaluator_factory()  # noqa: SLF001
    feedback = svc._feedback_factory()  # noqa: SLF001
    assert isinstance(evaluator, EvaluatorAgent)
    assert isinstance(feedback, FeedbackAgent)
    # 默认 factory 必须注入 LLM（不再是 mock 路径）
    assert evaluator.llm is not None
    assert feedback.llm is not None

    session = _fake_session("sess-default")
    bundle = await svc.run(session)

    assert bundle.status == "done"
    assert isinstance(bundle.evaluation, EvaluationReport)
    assert isinstance(bundle.feedback, TeacherFeedback)
    # 无 API key → evaluator 内部降级
    assert bundle.evaluation.overall == "unavailable"
    # feedback 在 evaluation unavailable 时短路走 fallback
    assert bundle.feedback.tone == "neutral"
    assert any("[fallback]" in s for s in bundle.feedback.strengths)
