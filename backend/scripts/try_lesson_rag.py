"""教案解析 + LLM 抽取 + Chroma 索引的冒烟测试脚本。

针对 data/lesson_samples/ 下的 6 份样例教案（覆盖 6 档学段）逐份运行：
1. parser: 解析 MD 或 PDF 为纯文本
2. extractor: 调用 LLM 抽取结构化元数据
3. indexer: 切片 + 写入 Chroma + 检索验证

验收基准从各份 meta.md 的 JSON 块自动解析，避免硬编码。

用法:
    cd backend
    uv run python scripts/try_lesson_rag.py              # 跑全部 6 份
    uv run python scripts/try_lesson_rag.py --only math_p3_fraction   # 只跑一份
    uv run python scripts/try_lesson_rag.py --skip-index  # 跳过 Chroma 索引省时间
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from llm.client import LLMClient
from rag.extractor import extract_lesson_meta
from rag.indexer import index_lesson, query_lesson
from rag.parser import parse_file

# 样例教案路径
SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "lesson_samples"

# 6 档学段 × 多份样例教案
# - 数学版：M1 首发，每学段 1 份（保留在前以兼容历史调用）
# - 跨学科版：M1/M2 增加（#83 + #73），每学段 ≥ 2 学科覆盖
SAMPLES: list[tuple[str, str]] = [
    # M1 首发：每学段 1 份数学
    ("p_lower", "math_p2_addition.md"),
    ("p_middle", "math_p3_fraction.md"),
    ("p_upper", "math_p5_area.md"),
    ("j_lower", "physics_j2_force.md"),
    ("j_upper", "math_j3_quadratic.md"),
    ("h", "math_h2_derivative.md"),
    # #83 跨学科扩展：覆盖 chinese / english / chemistry
    ("p_middle", "chinese_p3_poetry.md"),
    ("j_lower", "english_j1_present_tense.md"),
    ("h", "chemistry_h1_redox.md"),
    # #73 (本期) 第二学科补足：p_lower / p_upper / j_upper 各加 1 学科
    # + 总数补到 ≥ 15
    ("p_lower", "chinese_p1_pinyin.md"),
    ("p_upper", "chinese_p5_metaphor.md"),
    ("j_lower", "history_j2_opium_war.md"),
    ("j_upper", "history_j3_xinhai.md"),
    ("j_upper", "biology_j3_genetics.md"),
    ("h", "politics_h1_economy.md"),
]


def _load_expected(meta_path: Path) -> dict:
    """从 meta.md 中解析首个 ```json ``` 块作为验收基准。"""
    content = meta_path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        raise ValueError(f"{meta_path} 中未找到 JSON 预期块")
    return json.loads(match.group(1))


def _check_field(actual: str, expected: str, mode: str = "contains_any") -> bool:
    """模糊字段校验：预期字符串中任一关键词（多年级/多课题关键词）出现在 actual 即算通过。"""
    if not actual or not expected:
        return False
    if mode == "exact":
        return actual == expected
    # 抽取 2-4 字的中文子串作候选关键词（简化：取 expected 的前两个字 + 后两个字）
    candidates = {expected, expected[:2], expected[-2:]}
    # 添加常用变体：“小学二年级”→“二年级”；“初一年”→“初一”等
    candidates.update(re.findall(r"[\u4e00-\u9fff]{2,4}", expected))
    return any(c and c in actual for c in candidates)


async def _run_single(
    llm: LLMClient, stage_id: str, filename: str, skip_index: bool
) -> bool:
    """对一份样例教案跑完整的 parse → extract → (index) 流程，返回是否验收通过。"""
    sample = SAMPLES_DIR / filename
    meta_path = sample.with_suffix(".meta.md")
    if not sample.exists():
        print(f"   ❌ 样例文件不存在: {sample}")
        return False
    if not meta_path.exists():
        print(f"   ❌ 验收基准不存在: {meta_path}")
        return False

    header = f" [{stage_id}] {filename} "
    print("\n" + header.center(60, "━"))

    expected = _load_expected(meta_path)

    # --- 1. Parser ---
    text = parse_file(sample)
    print(f"📄 解析 {len(text)} 字符")

    # --- 2. Extractor ---
    print("🤖 LLM 抽取中...")
    meta = await extract_lesson_meta(llm, text)
    print(f"   学科: {meta.subject}  |  年级: {meta.grade}  |  课题: {meta.topic}")
    print(
        f"   objectives={len(meta.objectives)}  key_points={len(meta.key_points)}  difficult_points={len(meta.difficult_points)}"
    )

    # --- 验收检查 ---
    checks = [
        (f"subject == {expected['subject']!r}", meta.subject == expected["subject"]),
        (
            f"grade 匹配 {expected['grade']!r}",
            _check_field(meta.grade, expected["grade"]),
        ),
        (
            f"topic 匹配 {expected['topic']!r}",
            _check_field(meta.topic, expected["topic"]),
        ),
        (
            f"objectives >= {max(3, len(expected['objectives']) // 2)} 条",
            len(meta.objectives) >= max(3, len(expected["objectives"]) // 2),
        ),
        (
            f"key_points >= {max(1, len(expected['key_points']) // 2)} 条",
            len(meta.key_points) >= max(1, len(expected["key_points"]) // 2),
        ),
        (
            f"difficult_points >= {max(1, len(expected['difficult_points']) // 2)} 条",
            len(meta.difficult_points)
            >= max(1, len(expected["difficult_points"]) // 2),
        ),
    ]
    all_pass = True
    for desc, ok in checks:
        status = "✅" if ok else "❌"
        print(f"   {status} {desc}")
        if not ok:
            all_pass = False

    # --- 3. Indexer ---
    if not skip_index:
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_count = index_lesson(f"smoke_{stage_id}", text, persist_dir=tmpdir)
            query = expected.get("key_points", [expected.get("topic", "")])[0]
            results = query_lesson(
                query, lesson_id=f"smoke_{stage_id}", persist_dir=tmpdir
            )
            print(f"📦 索引 {chunk_count} 片 · 检索 {query!r} → {len(results)} 条结果")

    return all_pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="教案解析 / 抽取 / 索引冒烟测试")
    parser.add_argument(
        "--only", help="只跑指定样例（文件名含不含 .md 都行）", default=None
    )
    parser.add_argument(
        "--skip-index", action="store_true", help="跳过 Chroma 索引阶段"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("教案解析冒烟测试：6 档学段 × 6 份样例教案")
    print("=" * 60)

    targets = SAMPLES
    if args.only:
        needle = args.only if args.only.endswith(".md") else f"{args.only}.md"
        targets = [(s, f) for s, f in SAMPLES if f == needle or f.startswith(args.only)]
        if not targets:
            print(f"❌ 未找到匹配 {args.only!r} 的样例")
            return

    llm = LLMClient()
    results: list[tuple[str, str, bool]] = []
    for stage_id, filename in targets:
        ok = await _run_single(llm, stage_id, filename, args.skip_index)
        results.append((stage_id, filename, ok))

    # --- 汇总 ---
    print("\n" + "=" * 60)
    print("📋 汇总")
    print("=" * 60)
    for stage_id, filename, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"   {status}  [{stage_id:<8}] {filename}")
    passed = sum(1 for _, _, ok in results if ok)
    total = len(results)
    print(f"\n通过率：{passed}/{total}")
    print("=" * 60)

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
