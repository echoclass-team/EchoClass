"""``kb.evolution.EvolutionEngine`` 单元测试。

覆盖：
- 观察事件写入
- 候选迷思状态机：合法 / 非法转换
- 锚点增删 + 审计 trail
- 不存在的目标抛错
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from kb import database as kb_db
from kb.evolution import EvolutionEngine
from kb.models import (
    MisconceptionCandidate,
    Observation,
    Theory,
    TheoryAnchor,
    TheoryTrait,
)


@pytest.fixture
def memory_db(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("ECHOCLASS_DB_URL", "sqlite:///:memory:")
    kb_db.reset_engine_for_testing()
    kb_db.create_all_tables()
    # 准备一个最小理论 + trait，供锚点测试用
    with kb_db.get_session() as s:
        s.add(
            Theory(
                id="t_evo",
                name_zh="进化测试",
                scholar="X",
                school="P",
                summary="x",
                references_json="[]",
                traits=[
                    TheoryTrait(
                        theory_id="t_evo",
                        trait_key="k",
                        label="L",
                        operational_rules_json='["r"]',
                    )
                ],
            )
        )
    yield
    kb_db.reset_engine_for_testing()


@pytest.fixture
def engine() -> EvolutionEngine:
    return EvolutionEngine()


# ============================================================ Observation


def test_record_observation_basic(memory_db, engine):
    obs_id = engine.record_observation(
        event_type="theory_confirmed",
        session_id="s1",
        theory_id="t_evo",
        trait_key="k",
        persona_id="P1",
        payload={"detail": "学生说'我不会'"},
    )
    assert obs_id > 0
    with kb_db.get_session() as s:
        obs = s.get(Observation, obs_id)
        assert obs.event_type == "theory_confirmed"
        assert obs.session_id == "s1"
        assert json.loads(obs.payload_json)["detail"] == "学生说'我不会'"


def test_record_observation_invalid_event_type(memory_db, engine):
    with pytest.raises(ValueError, match="非法 event_type"):
        engine.record_observation(event_type="bogus")


# ============================================================ 候选迷思状态机


def _submit_candidate(engine: EvolutionEngine) -> int:
    return engine.submit_misconception_candidate(
        student_text="分母大的分数就大",
        suggested={"subject": "数学", "key_point": "分数比较"},
        session_id="s2",
    )


def test_submit_candidate_creates_audit(memory_db, engine):
    cid = _submit_candidate(engine)
    with kb_db.get_session() as s:
        cand = s.get(MisconceptionCandidate, cid)
        assert cand.status == "candidate"
        # 应有一条 misconception_candidate 审计 observation
        obs_count = (
            s.query(Observation)
            .filter_by(event_type="misconception_candidate")
            .count()
        )
        assert obs_count == 1


def test_candidate_full_review_flow_approved(memory_db, engine):
    """candidate → reviewing → approved，每步都有审计。"""
    cid = _submit_candidate(engine)
    engine.assign_candidate_for_review(cid, reviewer_id="rev1")
    engine.review_candidate(
        cid, decision="approved", reviewer_id="rev1", notes="确实是常见迷思"
    )

    with kb_db.get_session() as s:
        cand = s.get(MisconceptionCandidate, cid)
        assert cand.status == "approved"
        assert cand.reviewer_id == "rev1"
        assert cand.reviewed_at is not None
        assert cand.review_notes == "确实是常见迷思"

        # 审计 observation：1 提交 + 2 状态变更
        candidate_reviewed = (
            s.query(Observation)
            .filter_by(event_type="candidate_reviewed")
            .all()
        )
        assert len(candidate_reviewed) == 2
        payloads = [json.loads(o.payload_json) for o in candidate_reviewed]
        assert {p["from"] for p in payloads} == {"candidate", "reviewing"}
        assert {p["to"] for p in payloads} == {"reviewing", "approved"}


def test_candidate_review_rejected(memory_db, engine):
    cid = _submit_candidate(engine)
    engine.review_candidate(
        cid, decision="rejected", reviewer_id="rev1", notes="重复"
    )
    with kb_db.get_session() as s:
        cand = s.get(MisconceptionCandidate, cid)
        assert cand.status == "rejected"


def test_candidate_review_merged_requires_target(memory_db, engine):
    cid = _submit_candidate(engine)
    with pytest.raises(ValueError, match="merged_into_id"):
        engine.review_candidate(
            cid, decision="merged", reviewer_id="rev1"
        )


def test_candidate_review_merged_with_target(memory_db, engine):
    cid = _submit_candidate(engine)
    engine.review_candidate(
        cid,
        decision="merged",
        reviewer_id="rev1",
        merged_into_id="mc_existing_001",
    )
    with kb_db.get_session() as s:
        cand = s.get(MisconceptionCandidate, cid)
        assert cand.status == "merged"
        assert cand.merged_into_id == "mc_existing_001"


def test_candidate_invalid_transition(memory_db, engine):
    """approved 之后不能再走 reviewing。"""
    cid = _submit_candidate(engine)
    engine.review_candidate(cid, decision="approved", reviewer_id="rev1")
    with pytest.raises(ValueError, match="非法状态转换"):
        engine.assign_candidate_for_review(cid, reviewer_id="rev1")


def test_candidate_not_found(memory_db, engine):
    with pytest.raises(LookupError):
        engine.review_candidate(
            999, decision="approved", reviewer_id="rev1"
        )


# ============================================================ Anchor 增删


def test_add_anchor_creates_with_audit(memory_db, engine):
    a = engine.add_anchor(
        theory_id="t_evo",
        trait_key="k",
        target_type="persona",
        target_id="郑宇凡",
    )
    assert a.id is not None
    with kb_db.get_session() as s:
        assert s.query(TheoryAnchor).count() == 1
        added = (
            s.query(Observation).filter_by(event_type="anchor_added").one()
        )
        payload = json.loads(added.payload_json)
        assert payload["target_id"] == "郑宇凡"


def test_add_anchor_idempotent(memory_db, engine):
    """重复 add_anchor 不应创建第二行，也不应再写审计。"""
    engine.add_anchor(
        theory_id="t_evo", trait_key="k",
        target_type="persona", target_id="P1",
    )
    engine.add_anchor(
        theory_id="t_evo", trait_key="k",
        target_type="persona", target_id="P1",
    )
    with kb_db.get_session() as s:
        assert s.query(TheoryAnchor).count() == 1
        assert (
            s.query(Observation).filter_by(event_type="anchor_added").count()
            == 1
        )


def test_add_anchor_invalid_target_type(memory_db, engine):
    with pytest.raises(ValueError, match="非法 target_type"):
        engine.add_anchor(
            theory_id="t_evo", trait_key="k",
            target_type="bogus", target_id="P1",
        )


def test_add_anchor_unknown_trait(memory_db, engine):
    with pytest.raises(ValueError, match="trait 不存在"):
        engine.add_anchor(
            theory_id="t_evo", trait_key="ghost",
            target_type="persona", target_id="P1",
        )


def test_remove_anchor_removes_with_audit(memory_db, engine):
    engine.add_anchor(
        theory_id="t_evo", trait_key="k",
        target_type="persona", target_id="P1",
    )
    removed = engine.remove_anchor(
        theory_id="t_evo", trait_key="k",
        target_type="persona", target_id="P1",
    )
    assert removed is True
    with kb_db.get_session() as s:
        assert s.query(TheoryAnchor).count() == 0
        assert (
            s.query(Observation).filter_by(event_type="anchor_removed").count()
            == 1
        )


def test_remove_anchor_missing_returns_false(memory_db, engine):
    removed = engine.remove_anchor(
        theory_id="t_evo", trait_key="k",
        target_type="persona", target_id="ghost_persona",
    )
    assert removed is False
    with kb_db.get_session() as s:
        # 不应写审计
        assert (
            s.query(Observation).filter_by(event_type="anchor_removed").count()
            == 0
        )
