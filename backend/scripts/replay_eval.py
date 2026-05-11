"""评估 replay 工具。

用途
----
对一份固定 session JSON 重复跑 ``EvaluatorAgent`` + ``FeedbackAgent``，
打印每次的维度分、overall、耗时与 token 统计；多次跑时计算方差，
便于 prompt 迭代时判断稳定性 + 定位"这次比上次差在哪个维度"。

CLI 示例
--------
::

    # 单跑（默认 rubric=v0）
    uv run python scripts/replay_eval.py data/demo_sessions/session_good.json

    # 重复 5 次取方差
    uv run python scripts/replay_eval.py data/demo_sessions/session_good.json --n 5

    # 双 rubric 对比（每个 rubric 跑 --n 次）
    uv run python scripts/replay_eval.py session_good.json --rubric v0 --rubric v1 --n 3

    # 不调真 LLM，走 mock（仅冒烟，无方差意义）
    uv run python scripts/replay_eval.py session_good.json --mock

    # 仅跑 evaluator，跳过 feedback
    uv run python scripts/replay_eval.py session_good.json --no-feedback

输入约定
--------
session JSON 必须满足 ``services.session_serde`` 的 v1 格式（同 demo_sessions）。

输出
----
纯文本，按 rubric 分组：

- 单次：维度分明细 + overall + latency + token + tone
- ``--n`` > 1：每维度均值 / 标准差 / min / max；overall 同样统计；
  并打印"相邻两次最大变动维度"，对应验收标准。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.evaluator import EvaluatorAgent
from agents.feedback import FeedbackAgent
from llm.client import LLMClient
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from services.session_serde import load_bundle_from_dict

logger = logging.getLogger(__name__)


# ============================================================ token 计数 wrapper


class _TokenTrackingLLM:
    """包装 ``LLMClient``，在每次 ``chat`` 调用后累加 token usage。

    duck-typed 给 ``EvaluatorAgent`` / ``FeedbackAgent`` 使用——它们只调用
    ``.chat(...)``，不依赖 LLMClient 的其它接口。
    """

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.calls: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    async def chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        resp = await self._inner.chat(messages, **kwargs)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        self.calls += 1
        return resp

    def reset(self) -> None:
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0


# ============================================================ 单次结果容器


@dataclass
class _RunResult:
    """单次 replay 的结果。"""

    rubric: str
    run_index: int  # 1-based
    evaluation: EvaluationReport
    feedback: TeacherFeedback | None
    eval_latency_ms: int
    feedback_latency_ms: int
    eval_tokens_in: int
    eval_tokens_out: int
    feedback_tokens_in: int
    feedback_tokens_out: int

    @property
    def total_latency_ms(self) -> int:
        return self.eval_latency_ms + self.feedback_latency_ms

    @property
    def total_tokens(self) -> int:
        return (
            self.eval_tokens_in
            + self.eval_tokens_out
            + self.feedback_tokens_in
            + self.feedback_tokens_out
        )


# ============================================================ 单次 replay


async def replay_once(
    *,
    session,
    rubric_version: str,
    run_index: int,
    use_mock: bool,
    skip_feedback: bool,
) -> _RunResult:
    """跑一次 evaluator (+ optional feedback)，返回 ``_RunResult``。

    ``use_mock=True`` 时构造 EvaluatorAgent / FeedbackAgent 不传 llm，走 mock 路径
    （不走网，token 全部为 0；用于冒烟，无方差意义）。
    """
    if use_mock:
        evaluator = EvaluatorAgent(rubric_version=rubric_version)
        feedback_agent = FeedbackAgent()
        eval_tracker: _TokenTrackingLLM | None = None
        feedback_tracker: _TokenTrackingLLM | None = None
    else:
        eval_tracker = _TokenTrackingLLM(LLMClient())
        feedback_tracker = _TokenTrackingLLM(LLMClient())
        evaluator = EvaluatorAgent(
            llm=eval_tracker,  # type: ignore[arg-type]
            rubric_version=rubric_version,
        )
        feedback_agent = FeedbackAgent(llm=feedback_tracker)  # type: ignore[arg-type]

    t0 = time.perf_counter()
    evaluation = await evaluator.evaluate(session)
    eval_latency_ms = int((time.perf_counter() - t0) * 1000)

    feedback: TeacherFeedback | None = None
    feedback_latency_ms = 0
    if not skip_feedback:
        t1 = time.perf_counter()
        feedback = await feedback_agent.generate(session, evaluation)
        feedback_latency_ms = int((time.perf_counter() - t1) * 1000)

    return _RunResult(
        rubric=rubric_version,
        run_index=run_index,
        evaluation=evaluation,
        feedback=feedback,
        eval_latency_ms=eval_latency_ms,
        feedback_latency_ms=feedback_latency_ms,
        eval_tokens_in=eval_tracker.prompt_tokens if eval_tracker else 0,
        eval_tokens_out=eval_tracker.completion_tokens if eval_tracker else 0,
        feedback_tokens_in=feedback_tracker.prompt_tokens if feedback_tracker else 0,
        feedback_tokens_out=feedback_tracker.completion_tokens
        if feedback_tracker
        else 0,
    )


# ============================================================ 输出


def _format_overall(overall: Any) -> str:
    if isinstance(overall, float):
        return f"{overall:.2f}"
    return str(overall)


def _print_run_header(result: _RunResult) -> None:
    overall = _format_overall(result.evaluation.overall)
    tone = result.feedback.tone if result.feedback else "—"
    print(
        f"  #{result.run_index}  overall={overall}  "
        f"eval={result.eval_latency_ms}ms  fb={result.feedback_latency_ms}ms  "
        f"tokens=({result.eval_tokens_in}+{result.eval_tokens_out})/"
        f"({result.feedback_tokens_in}+{result.feedback_tokens_out})  tone={tone}"
    )
    if result.evaluation.scores:
        dim_str = "  ".join(
            f"{s.dimension}={s.score}" for s in result.evaluation.scores
        )
        print(f"      {dim_str}")


def _stats_block(values: list[float]) -> dict[str, float]:
    """对一组数值计算 mean / stdev / min / max。"""
    if not values:
        return {"mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": statistics.fmean(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _print_aggregate(rubric: str, runs: list[_RunResult]) -> None:
    if not runs:
        return

    # overall 仅取 numeric 跑次
    numeric_overalls = [
        float(r.evaluation.overall)
        for r in runs
        if isinstance(r.evaluation.overall, (int, float))
    ]
    overall_stats = _stats_block(numeric_overalls)

    # 维度分聚合
    by_dim: dict[str, list[float]] = {}
    for r in runs:
        for s in r.evaluation.scores:
            by_dim.setdefault(s.dimension, []).append(float(s.score))

    print(f"\n  ── {rubric} 聚合（n={len(runs)}）──")
    if numeric_overalls:
        print(
            f"    overall  mean={overall_stats['mean']:.2f}  "
            f"stdev={overall_stats['stdev']:.2f}  "
            f"min={overall_stats['min']:.2f}  max={overall_stats['max']:.2f}"
        )
    else:
        print("    overall  (全部 unavailable，无均值)")

    for dim, scores in by_dim.items():
        st = _stats_block(scores)
        print(
            f"    {dim:6s}  mean={st['mean']:.2f}  "
            f"stdev={st['stdev']:.2f}  "
            f"min={st['min']:.0f}  max={st['max']:.0f}"
        )

    # 相邻跑次最大变动维度（验收标准：能定位"这次比上次差在哪个维度"）
    if len(runs) >= 2:
        print("    相邻跑次最大变动维度：")
        for i in range(1, len(runs)):
            prev = {s.dimension: s.score for s in runs[i - 1].evaluation.scores}
            cur = {s.dimension: s.score for s in runs[i].evaluation.scores}
            common = set(prev) & set(cur)
            if not common:
                continue
            diffs = sorted(
                ((d, cur[d] - prev[d]) for d in common),
                key=lambda x: abs(x[1]),
                reverse=True,
            )
            top_dim, top_delta = diffs[0]
            sign = "+" if top_delta > 0 else ""
            print(
                f"      #{i} → #{i + 1}: {top_dim} {sign}{top_delta} "
                f"(其余维度变化 ≤ {abs(diffs[1][1]) if len(diffs) > 1 else 0})"
            )

    # token + 耗时合计
    total_tokens = sum(r.total_tokens for r in runs)
    total_latency = sum(r.total_latency_ms for r in runs)
    print(f"    合计  total_tokens={total_tokens}  total_latency={total_latency}ms")


# ============================================================ 主流程


async def run(
    *,
    session_path: Path,
    rubrics: list[str],
    n: int,
    use_mock: bool,
    skip_feedback: bool,
) -> int:
    if not session_path.exists():
        print(f"❌ session 文件不存在：{session_path}", file=sys.stderr)
        return 1

    data = json.loads(session_path.read_text(encoding="utf-8"))
    bundle = load_bundle_from_dict(data)
    session = bundle.session

    print(f"▶ replay session: {session_path.name}")
    print(
        f"  session_id={session.id}  dialogs={len(session.dialogs)}  "
        f"label={bundle.label}  rubrics={rubrics}  n={n}  mock={use_mock}"
    )

    all_runs: list[_RunResult] = []
    for rubric in rubrics:
        print(f"\n● rubric={rubric}")
        runs: list[_RunResult] = []
        for i in range(1, n + 1):
            try:
                result = await replay_once(
                    session=session,
                    rubric_version=rubric,
                    run_index=i,
                    use_mock=use_mock,
                    skip_feedback=skip_feedback,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  #{i}  ❌ failed: {exc}", file=sys.stderr)
                continue
            runs.append(result)
            _print_run_header(result)
        if n > 1:
            _print_aggregate(rubric, runs)
        all_runs.extend(runs)

    return 0 if all_runs else 2


# ============================================================ CLI


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replay_eval",
        description=(
            "对固定 session JSON 重复跑 Evaluator + Feedback，"
            "输出维度分 / 耗时 / token / 方差。"
        ),
    )
    parser.add_argument(
        "session_json",
        type=Path,
        help="session JSON 路径（services.session_serde v1 格式）",
    )
    parser.add_argument(
        "--rubric",
        action="append",
        default=None,
        help="rubric 版本（可重复，每个版本跑 --n 次）。默认 v0",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="每个 rubric 重复跑次数（>1 时打印方差）",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="走 mock 路径（不调真 LLM，用于冒烟）",
    )
    parser.add_argument(
        "--no-feedback",
        action="store_true",
        help="只跑 evaluator，跳过 feedback",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_argparser().parse_args(argv)

    if args.n < 1:
        print("❌ --n 必须 >= 1", file=sys.stderr)
        return 2

    rubrics: list[str] = args.rubric or ["v0"]

    return asyncio.run(
        run(
            session_path=args.session_json,
            rubrics=rubrics,
            n=args.n,
            use_mock=args.mock,
            skip_feedback=args.no_feedback,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
