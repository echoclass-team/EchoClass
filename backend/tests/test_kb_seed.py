"""``scripts/seed_edu_kb.py`` 与 ``kb.poc_loader`` DB 路径的端到端测试。

测试策略：
- 每个测试自己起 :memory: 库
- 用临时目录放 1-2 张精简的 fixture 卡片 / persona JSON
- 跑 seed 脚本的 ``run()`` 函数（避免 subprocess 开销）
- 验证：导入数量正确 / 幂等 / 删除一致性 / poc_loader DB 路径返回的卡片
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from kb import database as kb_db
from kb import poc_loader
from kb.models import Theory, TheoryAnchor, TheoryTrait
from scripts.seed_edu_kb import run as seed_run


@pytest.fixture
def memory_db(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("ECHOCLASS_DB_URL", "sqlite:///:memory:")
    kb_db.reset_engine_for_testing()
    poc_loader.clear_cache()
    yield
    kb_db.reset_engine_for_testing()
    poc_loader.clear_cache()


@pytest.fixture
def fixture_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """两张精简的 fixture：1 个 theory（含 2 traits）+ 1 个 persona（带 anchors）。"""
    theories_dir = tmp_path / "edu_theories"
    personas_dir = tmp_path / "personas"
    theories_dir.mkdir()
    personas_dir.mkdir()

    (theories_dir / "fixture_theory.json").write_text(
        json.dumps({
            "id": "fixture_theory",
            "name_zh": "测试理论",
            "name_en": "Test",
            "scholar": "Tester (2026)",
            "year": 2026,
            "school": "测试派",
            "summary": "用于单元测试的最小理论。",
            "traits": {
                "alpha": {
                    "label": "α 类",
                    "operational_rules": ["规则 1", "规则 2"],
                },
                "beta": {
                    "label": "β 类",
                    "operational_rules": ["规则 3"],
                },
            },
            "applies_to": {"persona": True},
            "references": ["Tester. (2026). Hello world."],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    (personas_dir / "fixture_p.json").write_text(
        json.dumps({
            "id": "00000000-0000-4000-8000-000000000001",
            "name": "测试同学",
            "gender": "男",
            "grade": "P3",
            "age": 9,
            "stage_id": "p_lower",
            "subject_level": "中等",
            "speech_style": "测试",
            "misconception_tendencies": ["x"],
            "attention_span": "medium",
            "behavior_traits": ["x"],
            "avatar_seed": "test",
            "summary": "测试用 persona",
            "theory_anchors": [
                {"theory_id": "fixture_theory", "trait": "alpha"},
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    return theories_dir, personas_dir


# ============================================================ Seed 基本路径


def test_seed_create_inserts_all(memory_db, fixture_dirs):
    theories_dir, personas_dir = fixture_dirs
    stats = seed_run(
        theories_dir=theories_dir,
        personas_dir=personas_dir,
        create=True, reset=False, dry_run=False,
    )
    assert stats == {
        "theories": 1,
        "new_traits": 2,
        "updated_traits": 0,
        "persona_anchors": 1,
    }

    with kb_db.get_session() as s:
        assert s.query(Theory).count() == 1
        assert s.query(TheoryTrait).count() == 2
        assert s.query(TheoryAnchor).count() == 1


def test_seed_idempotent(memory_db, fixture_dirs):
    """重跑不重复行，trait 变成 'updated' 而非 'new'。"""
    theories_dir, personas_dir = fixture_dirs
    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=True, reset=False, dry_run=False,
    )
    stats2 = seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=False, reset=False, dry_run=False,
    )
    assert stats2["new_traits"] == 0
    assert stats2["updated_traits"] == 2

    with kb_db.get_session() as s:
        assert s.query(Theory).count() == 1
        assert s.query(TheoryTrait).count() == 2
        assert s.query(TheoryAnchor).count() == 1


def test_seed_removes_orphan_traits(memory_db, fixture_dirs):
    """JSON 删了一个 trait，重跑应同步删除 DB 里的 orphan trait。"""
    theories_dir, personas_dir = fixture_dirs
    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=True, reset=False, dry_run=False,
    )

    # 改 fixture：去掉 beta trait
    src = theories_dir / "fixture_theory.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    del data["traits"]["beta"]
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=False, reset=False, dry_run=False,
    )
    with kb_db.get_session() as s:
        assert s.query(TheoryTrait).count() == 1
        assert s.query(TheoryTrait).filter_by(trait_key="beta").count() == 0


def test_seed_removes_orphan_anchors(memory_db, fixture_dirs):
    """persona JSON 删了一个 anchor，重跑应同步删除 DB 锚点。"""
    theories_dir, personas_dir = fixture_dirs
    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=True, reset=False, dry_run=False,
    )

    src = personas_dir / "fixture_p.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    data["theory_anchors"] = []  # 清空
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=False, reset=False, dry_run=False,
    )
    with kb_db.get_session() as s:
        assert s.query(TheoryAnchor).count() == 0


def test_seed_dry_run(memory_db, fixture_dirs):
    """dry-run 不写库。"""
    theories_dir, personas_dir = fixture_dirs
    stats = seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=False, reset=False, dry_run=True,
    )
    assert stats == {"theories": 1, "traits": 2, "anchors": 1}
    # 库表都没建过，连接到时只剩空 schema
    kb_db.create_all_tables()
    with kb_db.get_session() as s:
        assert s.query(Theory).count() == 0


# ============================================================ poc_loader DB 路径


def test_poc_loader_db_after_seed(memory_db, fixture_dirs):
    """seed 完后 poc_loader 用 DB 路径能拿到一致内容。"""
    theories_dir, personas_dir = fixture_dirs
    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=True, reset=False, dry_run=False,
    )

    poc_loader.clear_cache()
    cards_db = poc_loader.load_theories(source="db")
    assert "fixture_theory" in cards_db
    card = cards_db["fixture_theory"]
    assert card.name_zh == "测试理论"
    assert set(card.traits.keys()) == {"alpha", "beta"}
    assert card.traits["alpha"].operational_rules == ["规则 1", "规则 2"]


def test_poc_loader_auto_falls_back_to_json(memory_db, fixture_dirs, tmp_path):
    """auto 模式下 DB 空 → fallback 到 JSON。"""
    theories_dir, _ = fixture_dirs
    kb_db.create_all_tables()  # 建表但不灌数据

    poc_loader.clear_cache()
    cards = poc_loader.load_theories(theories_dir=theories_dir, source="auto")
    assert "fixture_theory" in cards


def test_poc_loader_force_db_empty_returns_empty(memory_db, fixture_dirs):
    """source='db' 强制路径，库空就返回空 dict。"""
    kb_db.create_all_tables()
    poc_loader.clear_cache()
    cards = poc_loader.load_theories(source="db")
    assert cards == {}


def test_resolve_persona_anchors_via_db(memory_db, fixture_dirs):
    """seed 完后用 resolve_persona_anchors（走 DB）拿到正确的 ResolvedTheory。"""
    from schemas.student import Persona, TheoryAnchor as PydanticAnchor

    theories_dir, personas_dir = fixture_dirs
    seed_run(
        theories_dir=theories_dir, personas_dir=personas_dir,
        create=True, reset=False, dry_run=False,
    )
    poc_loader.clear_cache()

    persona = Persona(
        name="X",
        behavior_traits=["x"],
        theory_anchors=[
            PydanticAnchor(theory_id="fixture_theory", trait="alpha")
        ],
    )
    resolved = poc_loader.resolve_persona_anchors(persona)
    assert len(resolved) == 1
    r = resolved[0]
    assert r.theory_id == "fixture_theory"
    assert r.trait_key == "alpha"
    assert r.rules == ["规则 1", "规则 2"]
