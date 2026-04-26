"""把 SQLite KB 里的理论卡片全量索引进 Chroma。

每个 ``(theory_id, trait_key)`` 是一个独立 doc。重跑会清掉旧 collection 重建。

用法::

    # 默认 ./chroma_data
    uv run python scripts/build_theory_index.py

    # 指定持久化目录
    uv run python scripts/build_theory_index.py --persist-dir ./tmp_chroma

    # 跑完做一次 sanity 检索
    uv run python scripts/build_theory_index.py --sanity-query "焦虑且不敢回答的学生"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 让脚本能 import backend/ 下的模块
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from kb.retrieval import index_all_theories, search_theories  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="Chroma 持久化目录（默认从 CHROMA_PERSIST_DIR 或 ./chroma_data）",
    )
    parser.add_argument(
        "--sanity-query",
        default=None,
        help="索引后跑一次检索验证（可选 query）",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="启用 INFO 日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )

    n = index_all_theories(persist_dir=args.persist_dir)
    print("=== build_theory_index 完成 ===")
    print(f"  indexed traits: {n}")

    if args.sanity_query:
        hits = search_theories(
            args.sanity_query,
            n_results=3,
            persist_dir=args.persist_dir,
        )
        print(f"\n=== sanity check: '{args.sanity_query}' ===")
        for i, h in enumerate(hits, 1):
            print(
                f"  {i}. {h['name_zh']} / {h['label']} (distance={h['distance']:.4f})"
            )


if __name__ == "__main__":
    main()
