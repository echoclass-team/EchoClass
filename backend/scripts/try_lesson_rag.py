"""Issue #19 冒烟测试 — 教案解析 + LLM 抽取 + Chroma 索引。

用法:
    cd backend
    uv run python scripts/try_lesson_rag.py

会依次测试:
1. parser: 解析样例教案 MD 文件
2. extractor: 调用 LLM 抽取结构化元数据
3. indexer: 切片 + 写入 Chroma + 检索验证
"""

from __future__ import annotations

import asyncio
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

SAMPLE_FILES = [
    "math_p3_fraction.md",
    "math_p5_area.md",
    "physics_j2_force.md",
]


async def main() -> None:
    print("=" * 60)
    print("Issue #19 冒烟测试：教案解析与 RAG 索引")
    print("=" * 60)

    # 选择第一个样例
    sample = SAMPLES_DIR / SAMPLE_FILES[0]
    if not sample.exists():
        print(f"❌ 样例文件不存在: {sample}")
        return

    # --- 1. Parser ---
    print(f"\n📄 [1/3] 解析文件: {sample.name}")
    text = parse_file(sample)
    print(f"   ✅ 解析成功，共 {len(text)} 字符（前 200 字）:")
    print(f"   {text[:200]}...")

    # --- 2. Extractor ---
    print("\n🤖 [2/3] 调用 LLM 抽取元数据...")
    llm = LLMClient()
    meta = await extract_lesson_meta(llm, text)
    print("   ✅ 抽取成功:")
    print(f"   学科: {meta.subject}")
    print(f"   年级: {meta.grade}")
    print(f"   课题: {meta.topic}")
    print(f"   教学目标 ({len(meta.objectives)} 条):")
    for i, obj in enumerate(meta.objectives, 1):
        print(f"     {i}. {obj}")
    print(f"   教学重点 ({len(meta.key_points)} 条):")
    for kp in meta.key_points:
        print(f"     - {kp}")
    print(f"   教学难点 ({len(meta.difficult_points)} 条):")
    for dp in meta.difficult_points:
        print(f"     - {dp}")

    # --- 验收检查 ---
    print("\n📋 验收检查:")
    checks = [
        ("subject == '数学'", meta.subject == "数学"),
        ("grade 含 '三年级'", "三年级" in meta.grade),
        ("topic 含 '分数'", "分数" in meta.topic),
        ("objectives >= 3 条", len(meta.objectives) >= 3),
        ("key_points >= 2 条", len(meta.key_points) >= 2),
        ("difficult_points >= 1 条", len(meta.difficult_points) >= 1),
    ]
    all_pass = True
    for desc, ok in checks:
        status = "✅" if ok else "❌"
        print(f"   {status} {desc}")
        if not ok:
            all_pass = False

    # --- 3. Indexer ---
    print(f"\n📦 [3/3] 切片 + Chroma 索引...")
    with tempfile.TemporaryDirectory() as tmpdir:
        chunk_count = index_lesson("smoke_test", text, persist_dir=tmpdir)
        print(f"   ✅ 索引成功，共 {chunk_count} 个切片")

        # 检索测试
        results = query_lesson("分数的含义", lesson_id="smoke_test", persist_dir=tmpdir)
        print(f"   🔍 检索 '分数的含义' → 返回 {len(results)} 个切片")
        if results:
            print(f"   首条结果（前 100 字）: {results[0][:100]}...")

    # --- 总结 ---
    print("\n" + "=" * 60)
    if all_pass:
        print("🎉 全部验收通过！Issue #19 冒烟测试成功。")
    else:
        print("⚠️  部分验收未通过，请检查 LLM 抽取结果。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
