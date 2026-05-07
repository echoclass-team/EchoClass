"""验证所有人设 JSON 文件是否符合 _schema.json 规范。"""
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("需要安装 jsonschema: pip install jsonschema")
    sys.exit(1)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PERSONAS_DIR = DATA_DIR / "personas"
THEORIES_DIR = DATA_DIR / "edu_theories"
MISCONCEPTIONS_DIR = DATA_DIR / "misconceptions"


def _load_theory_traits() -> dict[str, set[str]]:
    """加载所有 edu_theories，返回 {theory_id: {trait_key, ...}}。"""
    out: dict[str, set[str]] = {}
    if not THEORIES_DIR.exists():
        return out
    for fp in THEORIES_DIR.glob("*.json"):
        if fp.name.startswith("_"):
            continue
        d = json.loads(fp.read_text(encoding="utf-8"))
        if "id" in d and "traits" in d:
            out[d["id"]] = set(d["traits"].keys())
    return out


def _load_misconception_ids() -> set[str]:
    """加载所有 misconceptions，返回 id 集合。"""
    ids: set[str] = set()
    if not MISCONCEPTIONS_DIR.exists():
        return ids
    for fp in MISCONCEPTIONS_DIR.glob("*.json"):
        if fp.name.startswith("_"):
            continue
        items = json.loads(fp.read_text(encoding="utf-8"))
        for it in items:
            if "id" in it:
                ids.add(it["id"])
    return ids


def main() -> None:
    schema_path = PERSONAS_DIR / "_schema.json"
    if not schema_path.exists():
        print(f"❌ Schema 文件不存在: {schema_path}")
        sys.exit(1)

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    persona_files = sorted(PERSONAS_DIR.glob("*.json"))
    persona_files = [p for p in persona_files if p.name != "_schema.json"]

    if not persona_files:
        print("❌ 没有找到人设 JSON 文件")
        sys.exit(1)

    theory_traits = _load_theory_traits()
    valid_misc_ids = _load_misconception_ids()

    print(f"📋 Schema: {schema_path.name}")
    print(
        f"📚 Cross-ref: {len(theory_traits)} theories, "
        f"{len(valid_misc_ids)} misconception ids"
    )
    print(f"📂 找到 {len(persona_files)} 个人设文件\n")

    all_ok = True
    for pf in persona_files:
        with open(pf, encoding="utf-8") as f:
            data = json.load(f)

        errors: list[str] = []

        # 1) JSON Schema 结构校验
        for err in jsonschema.Draft7Validator(schema).iter_errors(data):
            errors.append(f"schema {err.json_path}: {err.message}")

        # 2) theory_anchors 交叉引用校验
        for a in data.get("theory_anchors", []):
            tid, trait = a.get("theory_id"), a.get("trait")
            if tid not in theory_traits:
                errors.append(f"theory_anchors: 未知 theory_id={tid!r}")
            elif trait not in theory_traits[tid]:
                errors.append(
                    f"theory_anchors: {tid} 下无 trait={trait!r}"
                    f"（可选: {sorted(theory_traits[tid])}）"
                )

        # 3) misconception_ids 交叉引用校验 (v1.4)
        for mid in data.get("misconception_ids", []):
            if mid not in valid_misc_ids:
                errors.append(f"misconception_ids: 未知 id={mid!r}")

        if errors:
            print(f"❌ {pf.name}:")
            for e in errors:
                print(f"   - {e}")
            all_ok = False
        else:
            field_count = len(data)
            n_anchor = len(data.get("theory_anchors", []))
            n_misc = len(data.get("misconception_ids", []))
            print(
                f"✅ {pf.name:30s} "
                f"字段={field_count:2d} "
                f"锚点={n_anchor} misc_ids={n_misc} "
                f"{data['name']} ({data['grade']})"
            )

    print()
    if all_ok:
        print(f"🎉 全部 {len(persona_files)} 个人设验证通过！")
    else:
        print("⚠️  有人设验证失败，请检查上方错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    main()
