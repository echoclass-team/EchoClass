"""把 ``data/edu_theories/*.json`` 与 ``data/personas/*.json`` 灌入 SQLite KB。

支持三种模式:

- 默认：增量 upsert（已存在则更新，不存在则插入）
- ``--reset``: 先 drop 再 create 全部 KB 表，再灌种子（开发常用）
- ``--dry-run``: 仅打印将要做什么，不写库
- ``--create``: 首次起库，跑 ``Base.metadata.create_all``（绕过 alembic，本期 DX 用）

import 逻辑:

1. 加载 ``data/edu_theories/*.json`` → ``kb_theory`` + ``kb_theory_trait``
2. 加载 ``data/personas/*.json``，对每个 persona 的 ``theory_anchors`` 字段
   生成 ``kb_theory_anchor`` 记录（target_type='persona', target_id=persona.name）
3. ``Misconception``/``Rubric`` 维度的锚点暂不批量导入（第二期 C 提供数据后再加）

幂等性:

- Upsert 用 (id) / 复合主键作为冲突键
- TheoryAnchor 用 (theory_id, trait_key, target_type, target_id) 唯一约束
- 重复跑不产生多余行，但会更新 updated_at

用法::

    # 首次起库
    uv run python scripts/seed_edu_kb.py --create
    # 重置 + 灌种子
    uv run python scripts/seed_edu_kb.py --reset
    # 仅看会做什么
    uv run python scripts/seed_edu_kb.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 让脚本能 import backend/ 下的模块
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from kb.database import (  # noqa: E402
    create_all_tables,
    drop_all_tables,
    get_session,
)
from kb.models import (  # noqa: E402
    Theory,
    TheoryAnchor,
    TheoryTrait,
)

logger = logging.getLogger("seed_edu_kb")

_REPO_ROOT = _BACKEND_DIR.parent
_DEFAULT_THEORIES_DIR = _REPO_ROOT / "data" / "edu_theories"
_DEFAULT_PERSONAS_DIR = _REPO_ROOT / "data" / "personas"


# ============================================================ 加载源数据


def _load_theory_jsons(theories_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fp in sorted(theories_dir.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def _load_persona_jsons(personas_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fp in sorted(personas_dir.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


# ============================================================ Upsert


def _upsert_theory(sess, data: dict[str, Any]) -> tuple[int, int]:
    """返回 (新增 trait 数, 更新 trait 数)。"""
    theory_id = data["id"]
    existing = sess.get(Theory, theory_id)

    payload = {
        "id": theory_id,
        "name_zh": data["name_zh"],
        "name_en": data.get("name_en", ""),
        "scholar": data["scholar"],
        "year": int(data.get("year", 0)),
        "school": data["school"],
        "summary": data["summary"],
        "references_json": json.dumps(data.get("references", []), ensure_ascii=False),
        "applies_to_json": json.dumps(data.get("applies_to", {}), ensure_ascii=False),
    }

    if existing is None:
        theory = Theory(**payload)
        sess.add(theory)
    else:
        for k, v in payload.items():
            if k == "id":
                continue
            setattr(existing, k, v)
        theory = existing

    # ---- traits 全量重写（trait 数量少，无需细粒度 diff）
    new_count = 0
    upd_count = 0
    incoming_keys: set[str] = set()
    traits_data: dict[str, Any] = data.get("traits", {})
    for trait_key, trait_payload in traits_data.items():
        incoming_keys.add(trait_key)
        existing_trait = sess.get(TheoryTrait, (theory_id, trait_key))
        rules_json = json.dumps(trait_payload["operational_rules"], ensure_ascii=False)
        if existing_trait is None:
            sess.add(
                TheoryTrait(
                    theory_id=theory_id,
                    trait_key=trait_key,
                    label=trait_payload["label"],
                    operational_rules_json=rules_json,
                )
            )
            new_count += 1
        else:
            existing_trait.label = trait_payload["label"]
            existing_trait.operational_rules_json = rules_json
            upd_count += 1

    # 删掉 JSON 里已不存在的 trait（保持库与文件一致）
    if existing is not None:
        for t in list(theory.traits):
            if t.trait_key not in incoming_keys:
                sess.delete(t)

    return new_count, upd_count


def _upsert_persona_anchors(sess, persona_data: dict[str, Any]) -> int:
    """根据 persona JSON 的 theory_anchors 生成 / 更新 kb_theory_anchor 行。

    返回写入的锚点数（新增 + 更新）。
    """
    anchors_in: list[dict[str, Any]] = persona_data.get("theory_anchors") or []
    persona_target_id = persona_data["name"]
    written = 0
    incoming_keys: set[tuple[str, str]] = set()
    for a in anchors_in:
        theory_id = a["theory_id"]
        trait_key = a["trait"]
        incoming_keys.add((theory_id, trait_key))
        # 查是否已存在
        stmt = select(TheoryAnchor).where(
            TheoryAnchor.theory_id == theory_id,
            TheoryAnchor.trait_key == trait_key,
            TheoryAnchor.target_type == "persona",
            TheoryAnchor.target_id == persona_target_id,
        )
        existing = sess.execute(stmt).scalar_one_or_none()
        if existing is None:
            sess.add(
                TheoryAnchor(
                    theory_id=theory_id,
                    trait_key=trait_key,
                    target_type="persona",
                    target_id=persona_target_id,
                )
            )
        # 已存在则什么也不改（confidence/evidence_count 是第二期 evolution 的事）
        written += 1

    # 删除 persona JSON 已经不要的旧锚点（保持一致性）
    stmt = select(TheoryAnchor).where(
        TheoryAnchor.target_type == "persona",
        TheoryAnchor.target_id == persona_target_id,
    )
    for existing in sess.execute(stmt).scalars().all():
        if (existing.theory_id, existing.trait_key) not in incoming_keys:
            sess.delete(existing)

    return written


# ============================================================ Main


def run(
    *,
    theories_dir: Path,
    personas_dir: Path,
    create: bool,
    reset: bool,
    dry_run: bool,
) -> dict[str, int]:
    """主流程。返回统计 dict。"""
    if dry_run:
        theories = _load_theory_jsons(theories_dir)
        personas = _load_persona_jsons(personas_dir)
        anchor_count = sum(len(p.get("theory_anchors") or []) for p in personas)
        trait_count = sum(len(t.get("traits", {})) for t in theories)
        print("[DRY RUN]")
        print(f"  Theory cards to upsert : {len(theories)}")
        print(f"  Theory traits to upsert: {trait_count}")
        print(
            f"  Personas with anchors  : {sum(1 for p in personas if p.get('theory_anchors'))}"
        )
        print(f"  Total persona anchors  : {anchor_count}")
        return {
            "theories": len(theories),
            "traits": trait_count,
            "anchors": anchor_count,
        }

    if reset:
        drop_all_tables()
        create_all_tables()
    elif create:
        create_all_tables()

    theories = _load_theory_jsons(theories_dir)
    personas = _load_persona_jsons(personas_dir)

    new_traits = upd_traits = 0
    with get_session() as sess:
        for t in theories:
            n, u = _upsert_theory(sess, t)
            new_traits += n
            upd_traits += u

    anchor_total = 0
    with get_session() as sess:
        for p in personas:
            anchor_total += _upsert_persona_anchors(sess, p)

    stats = {
        "theories": len(theories),
        "new_traits": new_traits,
        "updated_traits": upd_traits,
        "persona_anchors": anchor_total,
    }
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theories-dir", default=str(_DEFAULT_THEORIES_DIR), type=Path)
    parser.add_argument("--personas-dir", default=str(_DEFAULT_PERSONAS_DIR), type=Path)
    parser.add_argument(
        "--create",
        action="store_true",
        help="首次起库：跑 Base.metadata.create_all（绕过 alembic）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="DROP + CREATE 全部 KB 表，再灌种子（开发常用）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要做什么，不写库",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="启用 INFO 日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )

    stats = run(
        theories_dir=Path(args.theories_dir),
        personas_dir=Path(args.personas_dir),
        create=args.create,
        reset=args.reset,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        print("=== seed_edu_kb 完成 ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
