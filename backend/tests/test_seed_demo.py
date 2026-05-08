"""``scripts/seed_demo`` 与 ``services/session_serde`` 的单元测试 (#M3-A7 / #128)。

覆盖：
- session_serde dump → load 往返保持等价
- 三份内置 fixture 构造合法
- 读盘 JSON 与 fixture 等价（防止 schema 漂移导致 JSON 过时）
- DB 灌库使用临时 SQLite，验证表行为符合预期
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import (
    Base,
    DialogMessageRecord,
    EvaluationRecord,
    FeedbackRecord,
    Lesson,
    QASessionRecord,
    User,
)
from scripts.seed_demo import (
    DEMO_DATA_DIR,
    DEMO_LESSON_ID,
    DEMO_SESSION_IDS,
    DEMO_USER_ID,
    _seed_bundle,
    _ensure_demo_lesson,
    _ensure_demo_user,
    _reset_demo_rows,
    build_all_bundles,
    read_bundles_from_disk,
    write_bundles_to_disk,
)
from services.session_serde import (
    dump_bundle_to_dict,
    load_bundle_from_dict,
)

# ============================================================ session_serde


def test_dump_load_roundtrip_preserves_session() -> None:
    """fixture → dump → load 后 session 关键字段保持等价。"""
    bundles = build_all_bundles()
    for original in bundles:
        payload = dump_bundle_to_dict(original)
        restored = load_bundle_from_dict(payload)

        assert restored.label == original.label
        assert restored.persona_ids == original.persona_ids
        assert restored.session.id == original.session.id
        assert restored.session.lesson_meta == original.session.lesson_meta
        assert set(restored.session.dialogs.keys()) == set(
            original.session.dialogs.keys()
        )
        for dialog_id, dialog in original.session.dialogs.items():
            assert restored.session.dialogs[dialog_id] == dialog
        assert restored.evaluation == original.evaluation
        assert restored.feedback == original.feedback


def test_load_rejects_unsupported_version() -> None:
    """旧版本 JSON 应被拒绝，避免 schema 漂移静默吞错。"""
    bundles = build_all_bundles()
    payload = dump_bundle_to_dict(bundles[0])
    payload["version"] = 999

    with pytest.raises(ValueError, match="unsupported session bundle version"):
        load_bundle_from_dict(payload)


# ============================================================ fixture 内容


def test_three_samples_cover_three_score_buckets() -> None:
    """good / mid / bad 三份样本必须落在三个分数段，作为 Pitch 切片素材。"""
    bundles = {b.label: b for b in build_all_bundles()}
    assert set(bundles.keys()) == {"good", "mid", "bad"}

    good_overall = bundles["good"].evaluation.overall  # type: ignore[union-attr]
    mid_overall = bundles["mid"].evaluation.overall  # type: ignore[union-attr]
    bad_overall = bundles["bad"].evaluation.overall  # type: ignore[union-attr]

    # 三档分数严格递减
    assert isinstance(good_overall, float)
    assert isinstance(mid_overall, float)
    assert isinstance(bad_overall, float)
    assert good_overall > mid_overall > bad_overall

    # tone 与分数段对齐
    assert bundles["good"].feedback.tone == "encouraging"  # type: ignore[union-attr]
    assert bundles["mid"].feedback.tone == "neutral"  # type: ignore[union-attr]
    assert bundles["bad"].feedback.tone == "critical"  # type: ignore[union-attr]


def test_disk_json_matches_fixture(tmp_path: Path) -> None:
    """仓库里 ``data/demo_sessions/*.json`` 必须与当前 fixture 一致；
    否则提示开发者跑一次 ``uv run python scripts/seed_demo.py --build`` 刷新。
    """
    fixture_bundles = {b.label: b for b in build_all_bundles()}

    for label in DEMO_SESSION_IDS:
        path = DEMO_DATA_DIR / f"session_{label}.json"
        assert path.exists(), (
            f"missing demo JSON: {path}; 跑 `uv run python scripts/seed_demo.py --build`"
        )
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        expected = dump_bundle_to_dict(fixture_bundles[label])
        assert on_disk == expected, (
            f"{path} 与 fixture 不一致；跑 --build 重新生成"
        )


def test_write_bundles_to_disk_uses_label(tmp_path: Path, monkeypatch) -> None:
    """write_bundles_to_disk 按 label 落盘到 DEMO_DATA_DIR。"""
    monkeypatch.setattr("scripts.seed_demo.DEMO_DATA_DIR", tmp_path)
    bundles = build_all_bundles()
    paths = write_bundles_to_disk(bundles)

    assert {p.name for p in paths} == {
        "session_good.json",
        "session_mid.json",
        "session_bad.json",
    }
    for p in paths:
        assert p.parent == tmp_path
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["version"] == 1


def test_read_bundles_from_disk_round_trips_real_files() -> None:
    """从仓库内的真实 JSON 文件读回，与 build_all_bundles 等价。"""
    fixture_bundles = {b.label: b for b in build_all_bundles()}
    on_disk_bundles = {b.label: b for b in read_bundles_from_disk()}
    assert set(on_disk_bundles) == set(fixture_bundles)
    for label, bundle in fixture_bundles.items():
        assert dump_bundle_to_dict(on_disk_bundles[label]) == dump_bundle_to_dict(
            bundle
        )


# ============================================================ DB 灌入（隔离 SQLite）


@pytest.fixture()
def db_session():
    """每个 DB 用例开一个独立 SQLite（内存）+ Session，避免污染主库。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_ensure_demo_user_is_idempotent(db_session) -> None:
    _ensure_demo_user(db_session)
    _ensure_demo_user(db_session)
    rows = db_session.query(User).filter(User.id == DEMO_USER_ID).all()
    assert len(rows) == 1
    assert rows[0].username == "demo"


def test_seed_bundle_writes_all_tables(db_session) -> None:
    """单个 bundle 灌入后，五张表都应有对应行。"""
    _ensure_demo_user(db_session)
    _ensure_demo_lesson(db_session)
    bundle = build_all_bundles()[0]  # good
    _seed_bundle(db_session, bundle)

    session_id = bundle.session.id
    assert (
        db_session.query(QASessionRecord).filter_by(id=session_id).count() == 1
    )
    msg_count = (
        db_session.query(DialogMessageRecord)
        .filter_by(session_id=session_id)
        .count()
    )
    assert msg_count == sum(
        len(d.messages) for d in bundle.session.dialogs.values()
    )
    assert (
        db_session.query(EvaluationRecord).filter_by(session_id=session_id).count()
        == 1
    )
    assert (
        db_session.query(FeedbackRecord).filter_by(session_id=session_id).count()
        == 1
    )


def test_reset_then_reseed_is_idempotent(db_session) -> None:
    """灌入 → reset → 重灌后行数与首次一致，验证 reset 路径干净。"""
    _ensure_demo_user(db_session)
    _ensure_demo_lesson(db_session)
    for bundle in build_all_bundles():
        _seed_bundle(db_session, bundle)
    first_count = db_session.query(QASessionRecord).count()
    assert first_count == 3

    _reset_demo_rows(db_session)
    assert db_session.query(QASessionRecord).count() == 0
    assert db_session.query(Lesson).filter_by(id=DEMO_LESSON_ID).count() == 0
    assert db_session.query(User).filter_by(id=DEMO_USER_ID).count() == 0

    _ensure_demo_user(db_session)
    _ensure_demo_lesson(db_session)
    for bundle in build_all_bundles():
        _seed_bundle(db_session, bundle)
    assert db_session.query(QASessionRecord).count() == first_count
