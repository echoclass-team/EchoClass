"""迷思库召回率链路验证。

离线脚本，不依赖 LLM / WebSocket / 数据库。直接做下列流程:

    data/lesson_samples/*.meta.md
        ↓ 解析每份教案的预期 JSON（subject / stage_id / key_points / topic）
    rag.misconceptions.match_misconceptions
        ↓
    统计每学段每份教案的命中数 → 算每学段平均

用途:

- C 端在不等 A 端 ``--debug-match`` 上线的情况下，独立完成 #73 任务 1 的
  "topic 与 key_points 召回率验证"。
- 输出可直接拷贝到 ``docs/m2_content_log.md`` 的 "召回率" 章节。

用法:

    cd backend
    uv run python scripts/check_misconception_recall.py
    uv run python scripts/check_misconception_recall.py --json   # 输出 JSON 格式便于汇总
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.misconceptions import match_misconceptions  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LESSONS_DIR = REPO_ROOT / "data" / "lesson_samples"

# 目标命中数
TARGET_HITS_PER_LESSON = 3


def _parse_meta(meta_path: Path) -> dict | None:
    """从 meta.md 中解析首个 ```json``` 代码块，返回 dict 或 None。"""
    content = meta_path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _collect_lessons() -> list[dict]:
    """扫描 data/lesson_samples/，返回每份教案的 meta dict 列表（按文件名排序）。"""
    out: list[dict] = []
    for md in sorted(LESSONS_DIR.glob("*.md")):
        if md.name.endswith(".meta.md"):
            continue
        meta_path = md.with_name(md.stem + ".meta.md")
        if not meta_path.exists():
            continue
        meta = _parse_meta(meta_path)
        if meta is None:
            continue
        meta["__file__"] = md.name
        out.append(meta)
    return out


def _run_recall(lesson: dict) -> list[dict]:
    """对单份教案跑 match_misconceptions，返回命中条目精简结构。"""
    hits = match_misconceptions(
        subject=lesson["subject"],
        stage_id=lesson["stage_id"],
        key_points=lesson.get("key_points", []),
        topic=lesson.get("topic", ""),
        difficult_points=lesson.get("difficult_points", []),
        limit=10,
    )
    return [{"id": h.id, "name": h.name, "topic": h.topic} for h in hits]


def main() -> None:
    parser = argparse.ArgumentParser(description="迷思库召回率链路验证")
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON 而不是人类可读表格"
    )
    args = parser.parse_args()

    lessons = _collect_lessons()
    results: list[dict] = []
    by_stage: dict[str, list[int]] = defaultdict(list)

    for lesson in lessons:
        hits = _run_recall(lesson)
        results.append(
            {
                "file": lesson["__file__"],
                "stage_id": lesson["stage_id"],
                "subject": lesson["subject"],
                "hit_count": len(hits),
                "hits": hits,
                "passed_target": len(hits) >= TARGET_HITS_PER_LESSON,
            }
        )
        by_stage[lesson["stage_id"]].append(len(hits))

    if args.json:
        print(
            json.dumps(
                {
                    "lessons": results,
                    "by_stage_avg": {
                        stage: round(sum(v) / len(v), 2)
                        for stage, v in by_stage.items()
                    },
                    "target_per_lesson": TARGET_HITS_PER_LESSON,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    # 人类可读表格
    print("=" * 80)
    print("迷思库召回率链路验证")
    print("=" * 80)
    print(f"目标：每份教案 ≥ {TARGET_HITS_PER_LESSON} 条命中")
    print()
    print(f"{'文件':<40} {'学段':<10} {'学科':<8} {'命中':<6} 状态")
    print("-" * 80)
    for r in results:
        status = "✅" if r["passed_target"] else "❌"
        print(
            f"{r['file']:<40} {r['stage_id']:<10} {r['subject']:<8} {r['hit_count']:<6} {status}"
        )

    print()
    print("=" * 80)
    print("每学段平均命中数")
    print("=" * 80)
    for stage in sorted(by_stage.keys()):
        vals = by_stage[stage]
        avg = sum(vals) / len(vals)
        flag = "✅" if avg >= TARGET_HITS_PER_LESSON else "❌"
        print(f"  {flag} {stage:<10} N={len(vals):<3} avg={avg:.2f}  vals={vals}")

    overall = sum(r["hit_count"] for r in results) / max(len(results), 1)
    print()
    print(f"总体平均：{overall:.2f} 条/份  (N={len(results)})")
    passed_total = sum(1 for r in results if r["passed_target"])
    print(f"达标教案：{passed_total}/{len(results)}")

    if any(not r["passed_target"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
