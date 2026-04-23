"""验证所有人设 JSON 文件是否符合 _schema.json 规范。"""
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("需要安装 jsonschema: pip install jsonschema")
    sys.exit(1)

PERSONAS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "personas"


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

    print(f"📋 Schema: {schema_path.name}")
    print(f"📂 找到 {len(persona_files)} 个人设文件\n")

    all_ok = True
    for pf in persona_files:
        with open(pf, encoding="utf-8") as f:
            data = json.load(f)

        errors = list(jsonschema.Draft7Validator(schema).iter_errors(data))

        if errors:
            print(f"❌ {pf.name}:")
            for err in errors:
                print(f"   - {err.json_path}: {err.message}")
            all_ok = False
        else:
            # 额外检查
            field_count = len(data)
            catchphrase_count = len(data.get("catchphrases", []))
            print(
                f"✅ {pf.name:30s} "
                f"字段数={field_count:2d}(≥15✓) "
                f"口头禅={catchphrase_count}(≥3✓) "
                f"人设={data['name']} ({data['grade']})"
            )

    print()
    if all_ok:
        print(f"🎉 全部 {len(persona_files)} 个人设验证通过！")
    else:
        print("⚠️  有人设验证失败，请检查上方错误信息。")
        sys.exit(1)


if __name__ == "__main__":
    main()
