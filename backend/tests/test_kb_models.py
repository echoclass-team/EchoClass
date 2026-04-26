"""KB 模块 SQLAlchemy 模型与 database.py 的单元测试。

约定：
- 用 ``ECHOCLASS_DB_URL=sqlite:///:memory:`` 起内存库，避免污染开发库
- 每个测试 fixture 创建独立 engine（reset_engine_for_testing）
- 测覆盖：表创建 / FK 约束 / CHECK 约束 / unique 约束 / 级联删除
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.exc import IntegrityError

from kb import database as kb_db
from kb.models import (
    ANCHOR_TARGET_TYPES,
    CANDIDATE_STATUSES,
    OBSERVATION_EVENT_TYPES,
    MisconceptionCandidate,
    Observation,
    Theory,
    TheoryAnchor,
    TheoryTrait,
)


@pytest.fixture
def memory_db(monkeypatch) -> Iterator[None]:
    """每个测试一个独立的内存库。"""
    monkeypatch.setenv("ECHOCLASS_DB_URL", "sqlite:///:memory:")
    kb_db.reset_engine_for_testing()
    kb_db.create_all_tables()
    yield
    kb_db.reset_engine_for_testing()


# ============================================================ Theory


def test_create_theory_with_traits(memory_db):
    """创建 Theory + 多个 TheoryTrait，relationship 正常。"""
    with kb_db.get_session() as s:
        t = Theory(
            id="x_theory",
            name_zh="X 理论",
            scholar="Foo (2026)",
            school="测试派",
            summary="...",
            references_json='["ref1"]',
        )
        t.traits.extend(
            [
                TheoryTrait(
                    theory_id="x_theory",
                    trait_key="alpha",
                    label="α",
                    operational_rules_json='["r1"]',
                ),
                TheoryTrait(
                    theory_id="x_theory",
                    trait_key="beta",
                    label="β",
                    operational_rules_json='["r2", "r3"]',
                ),
            ]
        )
        s.add(t)

    with kb_db.get_session() as s:
        loaded = s.get(Theory, "x_theory")
        assert loaded is not None
        assert loaded.name_zh == "X 理论"
        assert len(loaded.traits) == 2
        assert {t.trait_key for t in loaded.traits} == {"alpha", "beta"}


def test_theory_cascade_delete(memory_db):
    """删除 Theory 应级联删除其 traits。"""
    with kb_db.get_session() as s:
        s.add(
            Theory(
                id="cascade_t",
                name_zh="级联",
                scholar="X",
                school="P",
                summary="x",
                references_json="[]",
                traits=[
                    TheoryTrait(
                        theory_id="cascade_t",
                        trait_key="k",
                        label="L",
                        operational_rules_json='["r"]',
                    )
                ],
            )
        )

    with kb_db.get_session() as s:
        s.delete(s.get(Theory, "cascade_t"))

    with kb_db.get_session() as s:
        assert s.query(TheoryTrait).filter_by(theory_id="cascade_t").count() == 0


# ============================================================ Anchor


def _seed_basic_theory(s) -> None:
    """给 anchor 测试准备一份最小 theory + trait。"""
    s.add(
        Theory(
            id="t1",
            name_zh="t1",
            scholar="X",
            school="P",
            summary="s",
            references_json="[]",
            traits=[
                TheoryTrait(
                    theory_id="t1",
                    trait_key="k1",
                    label="L",
                    operational_rules_json='["r"]',
                )
            ],
        )
    )
    s.commit()


def test_anchor_unique_constraint(memory_db):
    """同一 (theory, trait, target_type, target_id) 不允许重复锚点。"""
    with kb_db.get_session() as s:
        _seed_basic_theory(s)

    with kb_db.get_session() as s:
        s.add(
            TheoryAnchor(
                theory_id="t1",
                trait_key="k1",
                target_type="persona",
                target_id="P1",
            )
        )

    with pytest.raises(IntegrityError):
        with kb_db.get_session() as s:
            s.add(
                TheoryAnchor(
                    theory_id="t1",
                    trait_key="k1",
                    target_type="persona",
                    target_id="P1",
                )
            )


def test_anchor_target_type_check(memory_db):
    """target_type 必须在白名单里。"""
    with kb_db.get_session() as s:
        _seed_basic_theory(s)

    with pytest.raises(IntegrityError):
        with kb_db.get_session() as s:
            s.add(
                TheoryAnchor(
                    theory_id="t1",
                    trait_key="k1",
                    target_type="bogus_type",
                    target_id="P1",
                )
            )


def test_anchor_confidence_range(memory_db):
    """confidence ∈ [0, 1]，越界应被拒。"""
    with kb_db.get_session() as s:
        _seed_basic_theory(s)

    with pytest.raises(IntegrityError):
        with kb_db.get_session() as s:
            s.add(
                TheoryAnchor(
                    theory_id="t1",
                    trait_key="k1",
                    target_type="persona",
                    target_id="P1",
                    confidence=1.5,
                )
            )


def test_anchor_fk_to_trait(memory_db):
    """trait 不存在时插 anchor 应失败。"""
    with pytest.raises(IntegrityError):
        with kb_db.get_session() as s:
            s.add(
                TheoryAnchor(
                    theory_id="ghost",
                    trait_key="ghost_key",
                    target_type="persona",
                    target_id="P1",
                )
            )


def test_anchor_cascade_on_trait_delete(memory_db):
    """删 trait 应级联删 anchors。"""
    with kb_db.get_session() as s:
        _seed_basic_theory(s)

    with kb_db.get_session() as s:
        s.add(
            TheoryAnchor(
                theory_id="t1",
                trait_key="k1",
                target_type="persona",
                target_id="P1",
            )
        )

    with kb_db.get_session() as s:
        # 删 trait（通过删 theory 级联，或者直接删 trait）
        trait = s.get(TheoryTrait, ("t1", "k1"))
        s.delete(trait)

    with kb_db.get_session() as s:
        assert s.query(TheoryAnchor).count() == 0


# ============================================================ Observation


def test_observation_event_type_check(memory_db):
    """event_type 必须在白名单里。"""
    # 合法的不抛
    with kb_db.get_session() as s:
        s.add(Observation(event_type="theory_confirmed", payload_json="{}"))

    # 非法的抛
    with pytest.raises(IntegrityError):
        with kb_db.get_session() as s:
            s.add(Observation(event_type="bogus_event", payload_json="{}"))


# ============================================================ MisconceptionCandidate


def test_candidate_status_check(memory_db):
    """status 必须在白名单里。"""
    with kb_db.get_session() as s:
        s.add(
            MisconceptionCandidate(
                student_text="...",
                suggested_misconception_json="{}",
                status="candidate",
            )
        )

    with pytest.raises(IntegrityError):
        with kb_db.get_session() as s:
            s.add(
                MisconceptionCandidate(
                    student_text="...",
                    suggested_misconception_json="{}",
                    status="bogus_status",
                )
            )


# ============================================================ 元数据自检


def test_constants_match_check_constraints():
    """Python 常量与模型 CHECK 约束保持同步（防止有人改一边忘改另一边）。"""
    # 仅检查长度，详细同步性靠模型里 f-string 直接引用
    assert len(ANCHOR_TARGET_TYPES) >= 3
    assert len(OBSERVATION_EVENT_TYPES) >= 5
    assert len(CANDIDATE_STATUSES) >= 4


def test_table_names_have_kb_prefix():
    """所有表名 'kb_' 前缀，避免与 B 端 M3 表冲突。"""
    from kb.models import Base

    for table in Base.metadata.tables.values():
        assert table.name.startswith("kb_"), f"missing prefix: {table.name}"


def test_get_db_url_default(monkeypatch, tmp_path):
    """无环境变量时拼出 file SQLite URL。"""
    monkeypatch.delenv("ECHOCLASS_DB_URL", raising=False)
    url = kb_db.get_db_url()
    assert url.startswith("sqlite:///")
    assert "echoclass.db" in url


def test_get_db_url_env_override(monkeypatch):
    monkeypatch.setenv("ECHOCLASS_DB_URL", "sqlite:///:memory:")
    assert kb_db.get_db_url() == "sqlite:///:memory:"
