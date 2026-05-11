"""离线校验 ``data/rubrics/<version>.json`` 是否合规。

用途
----

- C 端在不依赖 LLM / 网络的前提下，自检 rubric 文件是否满足
  ``data/rubrics/_schema.json`` 定义的契约
- 给 A 端 ``tests/test_evaluator.py::test_rubric_load`` 提供 import 友好的
  loader：本脚本既可作 CLI 使用，``load_rubric()`` 也可被测试 import

执行
----

::

    cd backend
    uv run python scripts/validate_rubric.py
    uv run python scripts/validate_rubric.py --version v0   # 显式指定
    uv run python scripts/validate_rubric.py --json         # 机器可读输出

退出码
------

- 0：所有 rubric 文件通过 schema + 业务规则
- 1：至少一个 rubric 文件不通过
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUBRICS_DIR = REPO_ROOT / "data" / "rubrics"
THEORIES_DIR = REPO_ROOT / "data" / "edu_theories"


def load_rubric(version: str = "v0") -> dict:
    """读取并返回 ``data/rubrics/<version>.json``。

    供 A 端测试 import 使用：

        from scripts.validate_rubric import load_rubric
        rubric = load_rubric("v0")
    """
    path = RUBRICS_DIR / f"{version}.json"
    if not path.exists():
        raise FileNotFoundError(f"Rubric not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads((RUBRICS_DIR / "_schema.json").read_text(encoding="utf-8"))


def _list_theory_ids() -> set[str]:
    """收集 ``data/edu_theories/*.json`` 中所有 ``id`` 字段。"""
    ids: set[str] = set()
    for f in THEORIES_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "id" in data:
            ids.add(data["id"])
    return ids


def validate_rubric_file(path: Path, schema: dict, theory_ids: set[str]) -> list[str]:
    """对单个 rubric 文件做 schema 校验 + 业务规则校验。

    返回错误列表（空表示通过）。
    """
    errors: list[str] = []
    try:
        rubric = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败：{e}"]

    # 1. JSON Schema 校验
    try:
        jsonschema.validate(rubric, schema)
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errors.append(f"schema: {loc} → {e.message}")

    # 2. 业务规则：维度 id 全大写、唯一
    dim_ids = [d["id"] for d in rubric.get("dimensions", [])]
    if len(dim_ids) != len(set(dim_ids)):
        errors.append(f"维度 id 不唯一：{dim_ids}")

    # 3. 业务规则：theory_anchors 必须能解析到 data/edu_theories/*.json
    for dim in rubric.get("dimensions", []):
        for anchor in dim.get("theory_anchors", []):
            if anchor not in theory_ids:
                errors.append(
                    f"维度 {dim['id']}: theory_anchor '{anchor}' "
                    f"在 data/edu_theories/ 中找不到对应卡片"
                )

    # 4. 业务规则：版本号与文件名一致
    expected_version = path.stem
    if rubric.get("version") != expected_version:
        errors.append(
            f"version 字段 ({rubric.get('version')!r}) 与文件名 ({expected_version!r}) 不一致"
        )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="离线校验 data/rubrics/*.json")
    parser.add_argument(
        "--version",
        default=None,
        help="只校验指定版本（如 v0），缺省时校验目录下所有 *.json",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true", help="机器可读输出"
    )
    args = parser.parse_args()

    schema = _load_schema()
    theory_ids = _list_theory_ids()

    if args.version:
        files = [RUBRICS_DIR / f"{args.version}.json"]
    else:
        files = sorted(
            p for p in RUBRICS_DIR.glob("*.json") if not p.name.startswith("_")
        )

    results: list[dict] = []
    for f in files:
        if not f.exists():
            results.append({"file": f.name, "ok": False, "errors": ["文件不存在"]})
            continue
        errs = validate_rubric_file(f, schema, theory_ids)
        results.append({"file": f.name, "ok": not errs, "errors": errs})

    if args.json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"已知 theory id（{len(theory_ids)} 张）：{sorted(theory_ids)}\n")
        for r in results:
            if r["ok"]:
                rubric = json.loads(
                    (RUBRICS_DIR / r["file"]).read_text(encoding="utf-8")
                )
                dims = [d["id"] for d in rubric["dimensions"]]
                print(f"✅ {r['file']:<20}  schema OK  dims={len(dims)} {dims}")
            else:
                print(f"❌ {r['file']}")
                for e in r["errors"]:
                    print(f"   - {e}")

    if any(not r["ok"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
