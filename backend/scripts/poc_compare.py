"""教育学知识库 POC 对比脚本。

目的
----
回答一个核心问题：**在 prompt 里注入教育学理论锚点（Bandura 自我效能感 / Vygotsky
ZPD），StudentAgent 生成的内容是否明显更专业、更像真实学生**？

方法
----
1. 取一个有 ``theory_anchors`` 的 persona（默认：p_upper_anxious 郑宇凡）
2. 准备一个能放大理论效应的对话场景（六年级数学，老师一次性讲了 3 步）
3. 用同一 persona 跑两组 N 次：
    - **baseline**: 通过 ``persona.model_copy(update={"theory_anchors": []})``
      清空锚点 → ``_resolve_theory_anchors`` 返回 []，等同旧 prompt
    - **with-theory**: 保留锚点 → prompt 里注入 Bandura + Vygotsky 的行为准则
4. 终端并排打印 N 轮结果 + 一份简单可量化指标（字数 / 是否说"懂了" / 是否含
   自我贬低词）
5. 输出到 ``docs/edu_kb_poc_results.md``，方便人工 review

用法
----
::

    # 默认 N=3，跑 anxious persona
    uv run python scripts/poc_compare.py

    # 指定其他 persona（必须该 persona 已有 theory_anchors）
    uv run python scripts/poc_compare.py --persona 郑宇凡 --n 5

    # 不写文件，只打印
    uv run python scripts/poc_compare.py --no-write

依赖
----
需要真实 LLM（``backend/.env`` 中 ``OPENAI_API_KEY`` 等已配置）。
跑一轮约 5-15 秒、几千 token。N=3 时总耗时约 1 分钟。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 让 backend/ 下的脚本能 import 同级模块
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 加载 backend/.env（与 main.py 一致）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_DIR / ".env")

from agents.student import StudentAgent  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from schemas.dialog import DialogReplyResult  # noqa: E402
from schemas.question import StudentQuestion  # noqa: E402
from schemas.student import Persona, load_personas  # noqa: E402

logger = logging.getLogger(__name__)


# ============================================================ POC 场景

# 场景：六年级数学"分数除法"。学生提了一个能体现迷思的问题，老师一次性讲了 3 步。
# 这个场景理论上能放大：
#   - low_self_efficacy → 学生不敢说"我懂了"，倾向回避
#   - needs_high_scaffolding → 学生听不进一次到位的解释，会要求拆步骤

SCENARIO_QUESTION = StudentQuestion(
    id="poc-q-001",
    speaker_id="anxious-poc",
    speaker_name="郑宇凡",
    content="老师，分数除法为什么要把后面那个翻过来再乘呀？我每次都搞反……",
    category="stuck_misconception",
    difficulty="medium",
    linked_key_point="分数除法的算法",
    linked_misconception_id=None,
    rationale="对'颠倒相乘'规则只记住步骤但不理解原理，且经常把哪个翻倒了搞混",
)

SCENARIO_TEACHER_UTTERANCE = (
    "好，我们一步一步来想啊。分数除法的关键是把除号变乘号、然后把后面那个分数颠倒。"
    "比如 1/2 除以 1/3，就变成 1/2 乘以 3/1，结果是 3/2。"
    "明白了吗？你试着算一下 1/3 除以 1/4 等于多少。"
)


# ============================================================ 简易指标


_SELF_DEPRECATION_WORDS = [
    "我太笨",
    "我笨",
    "我不会",
    "我不行",
    "我做不到",
    "我搞不懂",
    "我学不会",
    "老师叫别人",
    "我可能学不会",
    "我学不来",
]
_SCAFFOLDING_REQUEST_WORDS = [
    "再讲一遍",
    "再说一遍",
    "我没听懂",
    "能不能慢一点",
    "我跟不上",
    "讲慢一点",
    "我没明白",
    "再说说",
    "再来一遍",
]


def _measure(reply: DialogReplyResult) -> dict[str, Any]:
    """对一条回复抽取轻量指标，便于汇总对比。"""
    text = reply.content
    return {
        "len": len(text),
        "self_resolved": reply.self_resolved,
        "has_self_deprecation": any(w in text for w in _SELF_DEPRECATION_WORDS),
        "has_scaffold_request": any(w in text for w in _SCAFFOLDING_REQUEST_WORDS),
        # 句末省略 / 犹豫词，简单粗略统计
        "hesitation_marks": len(re.findall(r"[……、,，]\s*$|\.\.\.|嗯+|呃+", text)),
    }


# ============================================================ 主流程


async def _run_one(
    persona: Persona,
    *,
    n: int,
    label: str,
) -> list[tuple[DialogReplyResult, dict[str, Any]]]:
    """同一 persona 跑 N 次 ``respond_in_dialog``，收集回复 + 指标。"""
    llm = LLMClient()
    agent = StudentAgent(llm=llm, persona=persona, stage=None)

    results: list[tuple[DialogReplyResult, dict[str, Any]]] = []
    for i in range(n):
        print(f"  [{label}] round {i + 1}/{n} ... ", end="", flush=True)
        try:
            reply = await agent.respond_in_dialog(
                question=SCENARIO_QUESTION,
                teacher_utterance=SCENARIO_TEACHER_UTTERANCE,
                dialog_history=[],
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc!r}")
            reply = DialogReplyResult(
                content=f"[ERROR] {exc!r}", self_resolved=False, raw=""
            )
        metrics = _measure(reply)
        results.append((reply, metrics))
        print(f"len={metrics['len']:3d}  resolved={metrics['self_resolved']}")
    return results


def _summarize(
    label: str, rows: list[tuple[DialogReplyResult, dict[str, Any]]]
) -> dict[str, Any]:
    """汇总一组 N 次结果的统计。"""
    if not rows:
        return {"label": label, "n": 0}
    metrics = [r[1] for r in rows]
    n = len(rows)
    return {
        "label": label,
        "n": n,
        "avg_len": round(sum(m["len"] for m in metrics) / n, 1),
        "self_resolved_rate": sum(1 for m in metrics if m["self_resolved"]) / n,
        "self_deprecation_rate": sum(1 for m in metrics if m["has_self_deprecation"])
        / n,
        "scaffold_request_rate": sum(1 for m in metrics if m["has_scaffold_request"])
        / n,
        "avg_hesitation_marks": round(
            sum(m["hesitation_marks"] for m in metrics) / n, 2
        ),
    }


def _format_markdown(
    persona: Persona,
    baseline_rows: list[tuple[DialogReplyResult, dict[str, Any]]],
    with_theory_rows: list[tuple[DialogReplyResult, dict[str, Any]]],
    baseline_summary: dict[str, Any],
    with_theory_summary: dict[str, Any],
) -> str:
    """把对比结果写成可 review 的 Markdown。"""
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines: list[str] = [
        "# 教育学知识库 POC — 对比结果",
        "",
        f"- 生成时间: {ts}",
        f"- Persona: **{persona.name}** ({persona.stage_id} / {persona.subject_level})",
        f"- 锚点: {[f'{a.theory_id}:{a.trait}' for a in persona.theory_anchors]}",
        f"- N (每组轮次): **{len(baseline_rows)}**",
        "",
        "## 场景",
        "",
        f"**学生提问**: {SCENARIO_QUESTION.content}",
        "",
        f"**老师回应**: {SCENARIO_TEACHER_UTTERANCE}",
        "",
        "## 量化指标对比",
        "",
        "| 指标 | Baseline (无理论) | With Theory | 变化 |",
        "|---|---|---|---|",
    ]

    def _delta(a: float, b: float) -> str:
        if a == b:
            return "—"
        sign = "+" if b > a else ""
        return f"{sign}{round(b - a, 2)}"

    for key, label in [
        ("avg_len", "平均字数"),
        ("self_resolved_rate", "[懂了] 触发率"),
        ("self_deprecation_rate", "自我贬低率"),
        ("scaffold_request_rate", "求重讲率"),
        ("avg_hesitation_marks", "犹豫标记/句"),
    ]:
        a = baseline_summary.get(key, 0)
        b = with_theory_summary.get(key, 0)
        lines.append(f"| {label} | {a} | {b} | {_delta(a, b)} |")

    lines.extend(["", "## 逐轮原文对照", ""])
    n = max(len(baseline_rows), len(with_theory_rows))
    for i in range(n):
        lines.append(f"### Round {i + 1}")
        lines.append("")
        lines.append("**Baseline (无理论)**:")
        lines.append("")
        if i < len(baseline_rows):
            r, _ = baseline_rows[i]
            lines.append(f"> {r.content}")
        else:
            lines.append("> (缺)")
        lines.append("")
        lines.append("**With Theory (Bandura + Vygotsky)**:")
        lines.append("")
        if i < len(with_theory_rows):
            r, _ = with_theory_rows[i]
            lines.append(f"> {r.content}")
        else:
            lines.append("> (缺)")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## 主观评估指引",
            "",
            "请人工 review 时关注：",
            "",
            "1. **风格差异是否显著**？With Theory 组是否更符合 Bandura 低自我效能感 + Vygotsky 强支架需求的描述？",
            "2. **是否过拟合理论**？With Theory 组是否变得套路化、千篇一律？",
            "3. **是否压制了人设细节**？口头禅、说话风格是否仍体现？",
            "4. **`[懂了]` 触发是否更克制**？符合 Posner 概念改变模型应不易过早 accommodate。",
            "",
            "Go / No-Go 判定建议：",
            "",
            "- ✅ **明显更专业** → 推进 L3 全栈实现（feat/edu-kb-foundation）",
            "- ❌ **区别不明显** → kill explore 分支，复盘 prompt 注入方式",
            "- ➖ **部分有效** → 缩小 L3 范围（如只做评估侧）",
        ]
    )
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=3, help="每组轮次（默认 3）")
    parser.add_argument(
        "--persona",
        type=str,
        default="郑宇凡",
        help="人设姓名（默认郑宇凡 / p_upper_anxious）",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="不写 docs/edu_kb_poc_results.md，仅终端输出",
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "❌ 未设置 OPENAI_API_KEY，无法跑真实 LLM。请配置 backend/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    personas = load_personas()
    target = next((p for p in personas if p.name == args.persona), None)
    if target is None:
        print(f"❌ 未找到 persona: {args.persona}", file=sys.stderr)
        sys.exit(1)
    if not target.theory_anchors:
        print(
            f"❌ persona '{args.persona}' 没有 theory_anchors，无法做对比",
            file=sys.stderr,
        )
        sys.exit(1)

    baseline_persona = target.model_copy(update={"theory_anchors": []})

    print(f"=== POC: {target.name} ({target.stage_id}) | N={args.n} ===")
    print(f"  锚点: {[f'{a.theory_id}:{a.trait}' for a in target.theory_anchors]}")
    print()
    print(">> Baseline (无理论注入)")
    baseline_rows = await _run_one(baseline_persona, n=args.n, label="baseline")
    print()
    print(">> With Theory (Bandura 低自我效能感 + Vygotsky 强支架)")
    with_theory_rows = await _run_one(target, n=args.n, label="with-theory")

    baseline_summary = _summarize("baseline", baseline_rows)
    with_theory_summary = _summarize("with-theory", with_theory_rows)

    # ---- 终端摘要
    print()
    print("=" * 60)
    print("汇总指标")
    print("=" * 60)
    for key in [
        "avg_len",
        "self_resolved_rate",
        "self_deprecation_rate",
        "scaffold_request_rate",
        "avg_hesitation_marks",
    ]:
        a = baseline_summary.get(key, 0)
        b = with_theory_summary.get(key, 0)
        print(f"  {key:25s}  baseline={a:<6}  with_theory={b}")

    # ---- 写文件
    if not args.no_write:
        md = _format_markdown(
            target,
            baseline_rows,
            with_theory_rows,
            baseline_summary,
            with_theory_summary,
        )
        out_path = _BACKEND_DIR.parent / "docs" / "edu_kb_poc_results.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print()
        print(f"✅ 结果已写入: {out_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
