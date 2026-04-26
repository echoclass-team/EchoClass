"""``kb.retrieval`` 测试。

只测**功能正确性**：索引建出来、能检索、过滤生效、metadata 完整。
不测召回质量（默认 embedding 是英文 MiniLM，中文召回弱，第二期会换）。

每个测试用 ``tmp_path`` 独立 chroma 持久化目录，避免污染 ./chroma_data。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from kb import database as kb_db
from kb.models import Theory, TheoryTrait
from kb.retrieval import index_all_theories, search_theories


@pytest.fixture
def memory_db_with_seed(monkeypatch) -> Iterator[None]:
    """:memory: 库 + 灌 2 张精简理论卡片（共 4 traits）。"""
    monkeypatch.setenv("ECHOCLASS_DB_URL", "sqlite:///:memory:")
    kb_db.reset_engine_for_testing()
    kb_db.create_all_tables()
    with kb_db.get_session() as s:
        s.add_all([
            Theory(
                id="theory_a",
                name_zh="A 理论",
                scholar="作者甲 (2020)",
                school="A 学派",
                year=2020,
                summary="A 理论的核心概念",
                references_json='["ref1"]',
                traits=[
                    TheoryTrait(
                        theory_id="theory_a", trait_key="alpha",
                        label="α 类",
                        operational_rules_json='["A 类学生表现 1", "A 类学生表现 2"]',
                    ),
                    TheoryTrait(
                        theory_id="theory_a", trait_key="beta",
                        label="β 类",
                        operational_rules_json='["A 反向表现"]',
                    ),
                ],
            ),
            Theory(
                id="theory_b",
                name_zh="B 理论",
                scholar="作者乙 (2021)",
                school="B 学派",
                year=2021,
                summary="B 理论与 A 不同",
                references_json='["ref2"]',
                traits=[
                    TheoryTrait(
                        theory_id="theory_b", trait_key="gamma",
                        label="γ 类",
                        operational_rules_json='["B 类学生表现"]',
                    ),
                    TheoryTrait(
                        theory_id="theory_b", trait_key="delta",
                        label="δ 类",
                        operational_rules_json='["B 反向表现"]',
                    ),
                ],
            ),
        ])
    yield
    kb_db.reset_engine_for_testing()


def test_index_all_theories_returns_count(memory_db_with_seed, tmp_path: Path):
    n = index_all_theories(persist_dir=str(tmp_path))
    assert n == 4  # 2 cards * 2 traits


def test_index_idempotent(memory_db_with_seed, tmp_path: Path):
    """重跑索引应保持相同 doc 数（先 delete 再 add）。"""
    index_all_theories(persist_dir=str(tmp_path))
    n2 = index_all_theories(persist_dir=str(tmp_path))
    assert n2 == 4

    # collection 里实际 doc 数也应是 4
    from kb.retrieval import get_chroma_client, COLLECTION_NAME
    client = get_chroma_client(str(tmp_path))
    coll = client.get_or_create_collection(COLLECTION_NAME)
    assert coll.count() == 4


def test_search_returns_hits_with_metadata(memory_db_with_seed, tmp_path: Path):
    """检索返回的命中含完整元数据。"""
    index_all_theories(persist_dir=str(tmp_path))
    hits = search_theories(
        "学生表现", n_results=4, persist_dir=str(tmp_path)
    )
    assert len(hits) == 4
    for h in hits:
        assert h["theory_id"] in {"theory_a", "theory_b"}
        assert h["trait_key"] in {"alpha", "beta", "gamma", "delta"}
        assert h["scholar"] in {"作者甲 (2020)", "作者乙 (2021)"}
        assert h["school"] in {"A 学派", "B 学派"}
        assert isinstance(h["distance"], float)
        # document 应包含 trait label
        assert h["label"] in h["document"]


def test_search_school_filter(memory_db_with_seed, tmp_path: Path):
    """按 school 过滤只返回该学派的命中。"""
    index_all_theories(persist_dir=str(tmp_path))
    hits = search_theories(
        "学生表现", n_results=10, school="A 学派",
        persist_dir=str(tmp_path),
    )
    assert len(hits) == 2  # theory_a 的两条 trait
    assert all(h["school"] == "A 学派" for h in hits)


def test_search_empty_collection(memory_db_with_seed, tmp_path: Path):
    """没建索引时检索应返回空列表，不抛错。"""
    hits = search_theories("query", persist_dir=str(tmp_path))
    assert hits == []


def test_index_no_data(monkeypatch, tmp_path: Path):
    """DB 空时索引返回 0，不抛错。"""
    monkeypatch.setenv("ECHOCLASS_DB_URL", "sqlite:///:memory:")
    kb_db.reset_engine_for_testing()
    kb_db.create_all_tables()
    try:
        n = index_all_theories(persist_dir=str(tmp_path))
        assert n == 0
    finally:
        kb_db.reset_engine_for_testing()
