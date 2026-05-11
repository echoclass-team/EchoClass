"""``scripts/replay_eval`` 单元测试。

覆盖：
- `_TokenTrackingLLM` 累加 prompt/completion tokens
- `replay_once` mock 路径返回合法结构
- `replay_once` 真实路径（用 stub LLM）token + latency 计数
- `_print_aggregate` 在多次跑时输出方差 + 相邻 diff
- `run` 主流程读取真实 demo JSON 文件
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from scripts.replay_eval import (
    _RunResult,
    _TokenTrackingLLM,
    _print_aggregate,
    replay_once,
    run,
)
from schemas.evaluation import EvaluationReport, RubricScore
from schemas.feedback import TeacherFeedback
from scripts.seed_demo import build_all_bundles


# ============================================================ helpers


def _good_session():
    return build_all_bundles()[0].session


def _make_eval_completion() -> SimpleNamespace:
    """伪 ChatCompletion，``content`` 是 evaluator 期望的 JSON。"""
    payload = {
        "scores": [
            {
                "dimension": "MR",
                "score": 3,
                "rationale": "stub rationale",
                "evidence": [],
            },
            {
                "dimension": "KC",
                "score": 2,
                "rationale": "stub rationale",
                "evidence": [],
            },
        ],
        "overall": 2.5,
    }
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=80),
    )


def _make_feedback_completion() -> SimpleNamespace:
    payload = {
        "strengths": ["stub strength"],
        "improvements": ["stub improvement"],
        "next_steps": ["stub next step"],
        "tone": "encouraging",
    }
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=200, completion_tokens=60),
    )


# ============================================================ _TokenTrackingLLM


async def test_token_tracking_accumulates_usage() -> None:
    inner = MagicMock()
    inner.chat = AsyncMock(
        side_effect=[_make_eval_completion(), _make_feedback_completion()]
    )
    tracker = _TokenTrackingLLM(inner)

    await tracker.chat([{"role": "user", "content": "x"}])
    await tracker.chat([{"role": "user", "content": "y"}])

    assert tracker.calls == 2
    assert tracker.prompt_tokens == 120 + 200
    assert tracker.completion_tokens == 80 + 60


async def test_token_tracking_handles_missing_usage() -> None:
    """LLM 响应缺 usage 字段时不应崩溃，计数维持原值。"""
    inner = MagicMock()
    inner.chat = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=None,
        )
    )
    tracker = _TokenTrackingLLM(inner)
    await tracker.chat([{"role": "user", "content": "x"}])
    assert tracker.calls == 1
    assert tracker.prompt_tokens == 0
    assert tracker.completion_tokens == 0


# ============================================================ replay_once mock 路径


async def test_replay_once_mock_returns_valid_result() -> None:
    session = _good_session()
    result = await replay_once(
        session=session,
        rubric_version="v0",
        run_index=1,
        use_mock=True,
        skip_feedback=False,
    )

    assert isinstance(result, _RunResult)
    assert result.rubric == "v0"
    assert result.run_index == 1
    assert isinstance(result.evaluation, EvaluationReport)
    assert isinstance(result.feedback, TeacherFeedback)
    # mock 路径不调真 LLM → 0 token
    assert result.eval_tokens_in == 0
    assert result.eval_tokens_out == 0
    assert result.feedback_tokens_in == 0
    assert result.feedback_tokens_out == 0


async def test_replay_once_skip_feedback() -> None:
    session = _good_session()
    result = await replay_once(
        session=session,
        rubric_version="v0",
        run_index=1,
        use_mock=True,
        skip_feedback=True,
    )
    assert result.feedback is None
    assert result.feedback_latency_ms == 0


# ============================================================ replay_once 真实路径（stub LLM）


async def test_replay_once_real_path_counts_tokens(monkeypatch) -> None:
    """真实路径应通过 _TokenTrackingLLM 累加 evaluator + feedback 的 token。"""

    # stub LLMClient：第 1 个实例返回 evaluator 用的 JSON，
    # 第 2 个实例返回 feedback 用的 JSON（replay_once 内部分别构造两个 LLMClient）
    class _FakeLLMClient:
        _instance_count = 0

        def __init__(self, *args, **kwargs):
            type(self)._instance_count += 1
            self._is_first = type(self)._instance_count == 1

        async def chat(self, messages, **kwargs):
            return (
                _make_eval_completion()
                if self._is_first
                else _make_feedback_completion()
            )

    monkeypatch.setattr("scripts.replay_eval.LLMClient", _FakeLLMClient)

    session = _good_session()
    result = await replay_once(
        session=session,
        rubric_version="v0",
        run_index=1,
        use_mock=False,
        skip_feedback=False,
    )

    # evaluator 用一个 _FakeLLMClient，feedback 用另一个；各自累计自己的 token
    assert result.eval_tokens_in == 120
    assert result.eval_tokens_out == 80
    assert result.feedback_tokens_in == 200
    assert result.feedback_tokens_out == 60
    # overall 来自 stub eval response
    assert result.evaluation.overall == 2.5
    assert result.feedback is not None
    assert result.feedback.tone == "encouraging"


# ============================================================ 聚合输出


def _stub_run(
    run_index: int, scores: list[tuple[str, int]], overall: float
) -> _RunResult:
    return _RunResult(
        rubric="v0",
        run_index=run_index,
        evaluation=EvaluationReport(
            session_id="sess-stub",
            rubric_version="v0",
            scores=[
                RubricScore(dimension=d, score=s, rationale="r", evidence=[])
                for d, s in scores
            ],
            overall=overall,
            generated_at=__import__("datetime").datetime(
                2026, 1, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        ),
        feedback=None,
        eval_latency_ms=100,
        feedback_latency_ms=0,
        eval_tokens_in=10,
        eval_tokens_out=20,
        feedback_tokens_in=0,
        feedback_tokens_out=0,
    )


def test_print_aggregate_outputs_stats_and_diff(capsys) -> None:
    runs = [
        _stub_run(1, [("MR", 3), ("KC", 2)], 2.5),
        _stub_run(2, [("MR", 4), ("KC", 2)], 3.0),
        _stub_run(3, [("MR", 4), ("KC", 1)], 2.5),
    ]
    _print_aggregate("v0", runs)
    out = capsys.readouterr().out

    # 聚合标题
    assert "v0 聚合（n=3）" in out
    # overall 均值 2.67
    assert "overall" in out and "mean=2.67" in out
    # 维度行
    assert "MR" in out and "KC" in out
    # 相邻 diff 段
    assert "相邻跑次最大变动维度" in out
    # #1→#2 最大变动是 MR +1
    assert "MR +1" in out
    # #2→#3 最大变动是 KC -1
    assert "KC -1" in out


def test_print_aggregate_handles_unavailable_overall(capsys) -> None:
    """全部 overall='unavailable' 时不应崩，应明示无均值。"""
    runs = [
        _stub_run(1, [("MR", 0)], 0.0),
        _stub_run(2, [("MR", 0)], 0.0),
    ]
    # 手工把 overall 改成 unavailable
    for r in runs:
        r.evaluation = r.evaluation.model_copy(update={"overall": "unavailable"})
    _print_aggregate("v0", runs)
    out = capsys.readouterr().out
    assert "全部 unavailable" in out


# ============================================================ 端到端：真实 demo JSON


def test_run_end_to_end_with_real_demo_json(tmp_path: Path) -> None:
    """读取 data/demo_sessions/session_good.json 跑 mock 路径。"""
    demo_path = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "demo_sessions"
        / "session_good.json"
    )
    assert demo_path.exists()

    rc = asyncio.run(
        run(
            session_path=demo_path,
            rubrics=["v0"],
            n=2,
            use_mock=True,
            skip_feedback=False,
        )
    )
    assert rc == 0


def test_run_returns_error_when_session_missing(tmp_path: Path) -> None:
    rc = asyncio.run(
        run(
            session_path=tmp_path / "ghost.json",
            rubrics=["v0"],
            n=1,
            use_mock=True,
            skip_feedback=False,
        )
    )
    assert rc == 1
