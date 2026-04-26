"""验证 data/misconceptions/*.json 的内容规范。

校验规则（在 jsonschema 基础上额外补强）：
1. JSON Schema 校验（_schema.json）
2. subject 必须为中文（无 ASCII 字母），避免再次出现 politics / history / geography 这种英文残留
3. 每个 stage 元素必须落在 data/stage_profiles/ 实际存在的 stage_id 白名单内
4. id 必须全局唯一（跨文件不重复）
5. 文件名约定：<subject_pinyin>_<stage_group>.json，stage_group ∈ {primary, junior, high}

用法：
    uv run python scripts/validate_misconceptions.py
退出码：0 全部通过；1 有错误
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("需要安装 jsonschema: pip install jsonschema")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MISCONCEPTIONS_DIR = REPO_ROOT / "data" / "misconceptions"
STAGE_PROFILES_DIR = REPO_ROOT / "data" / "stage_profiles"

ALLOWED_STAGE_GROUPS = {"primary", "junior", "high"}


def _has_ascii_letter(text: str) -> bool:
    return any(("a" <= c.lower() <= "z") for c in text)


def _load_stage_whitelist() -> set[str]:
    """以 data/stage_profiles/ 实际文件名为权威源生成 stage_id 白名单。"""
    if not STAGE_PROFILES_DIR.exists():
        print(f"❌ stage_profiles 目录不存在: {STAGE_PROFILES_DIR}")
        sys.exit(1)
    return {fp.stem for fp in STAGE_PROFILES_DIR.glob("*.json") if not fp.name.startswith("_")}


def main() -> None:
    schema_path = MISCONCEPTIONS_DIR / "_schema.json"
    if not schema_path.exists():
        print(f"❌ Schema 文件不存在: {schema_path}")
        sys.exit(1)

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    stage_whitelist = _load_stage_whitelist()

    files = sorted(p for p in MISCONCEPTIONS_DIR.glob("*.json") if not p.name.startswith("_"))
    if not files:
        print("❌ data/misconceptions/ 下未找到任何迷思 JSON 文件")
        sys.exit(1)

    print(f"📋 Schema:           {schema_path.name}")
    print(f"🏷️  Stage 白名单:    {sorted(stage_whitelist)}")
    print(f"📂 找到 {len(files)} 个迷思文件\n")

    errors_by_file: dict[str, list[str]] = defaultdict(list)
    id_origin: dict[str, str] = {}
    total_items = 0
    subject_counts: dict[str, int] = defaultdict(int)
    stage_counts: dict[str, int] = defaultdict(int)

    for fp in files:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        rel = fp.name

        # ---- 1) JSON Schema -----------------------------------------------
        for err in jsonschema.Draft7Validator(schema).iter_errors(data):
            errors_by_file[rel].append(f"schema {list(err.absolute_path)}: {err.message}")

        # ---- 2/3/4) 业务规则 ----------------------------------------------
        if not isinstance(data, list):
            errors_by_file[rel].append("顶层必须是数组")
            continue

        for idx, item in enumerate(data):
            label = f"[{idx}] id={item.get('id', '<missing>')}"

            # subject 中文校验
            subject = item.get("subject", "")
            if not subject:
                errors_by_file[rel].append(f"{label} 缺少 subject")
            elif _has_ascii_letter(subject):
                errors_by_file[rel].append(
                    f"{label} subject={subject!r} 含 ASCII 字母，应为中文（如 politics → 政治）"
                )
            else:
                subject_counts[subject] += 1

            # stage 白名单校验
            stages = item.get("stage") or []
            if not stages:
                errors_by_file[rel].append(f"{label} stage 数组为空")
            for s in stages:
                if s not in stage_whitelist:
                    errors_by_file[rel].append(
                        f"{label} stage={s!r} 不在白名单 {sorted(stage_whitelist)}"
                    )
                else:
                    stage_counts[s] += 1

            # id 全局唯一校验
            iid = item.get("id")
            if iid:
                if iid in id_origin:
                    errors_by_file[rel].append(
                        f"{label} id 重复，已在 {id_origin[iid]} 出现"
                    )
                else:
                    id_origin[iid] = rel

            total_items += 1

        # ---- 5) 文件名约定（软规则，仅警告） ------------------------------
        parts = fp.stem.split("_")
        if len(parts) < 2 or parts[-1] not in ALLOWED_STAGE_GROUPS:
            errors_by_file[rel].append(
                f"文件名不符合约定 <subject>_<{'/'.join(sorted(ALLOWED_STAGE_GROUPS))}>.json"
            )

    # ============================================================== 输出
    all_ok = True
    for fp in files:
        rel = fp.name
        n_items = len(json.load(open(fp, encoding="utf-8")))
        if errors_by_file[rel]:
            all_ok = False
            print(f"❌ {rel:30s} n={n_items:3d}")
            for e in errors_by_file[rel]:
                print(f"   - {e}")
        else:
            print(f"✅ {rel:30s} n={n_items:3d}")

    print()
    print(f"📊 总条数:   {total_items}")
    print(f"📊 学科分布: {dict(sorted(subject_counts.items(), key=lambda kv: -kv[1]))}")
    print(f"📊 学段分布: {dict(sorted(stage_counts.items()))}")
    print()

    if all_ok:
        print(f"🎉 全部 {len(files)} 个迷思文件 / {total_items} 条迷思校验通过！")
        sys.exit(0)
    else:
        print("⚠️  存在校验失败，请按上方提示修复。")
        sys.exit(1)


if __name__ == "__main__":
    main()
