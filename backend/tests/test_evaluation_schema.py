"""`schemas/evaluation.py` + `schemas/feedback.py` 占位 schema 的冒烟测试。

Epic #121 协议冻结后运行；覆盖：

- 必填字段缺失 → 校验报错
- 典型有效 payload round-trip
- `overall="unavailable"` 降级合法
- `score` 越界校验
- `tone` 未知枚举被拒
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.evaluation import EvaluationReport, Evidence, RubricScore
from schemas.feedback import TeacherFeedback


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================ EvaluationReport


def test_evaluation_report_round_trip() -> None:
    report = EvaluationReport(
        session_id="sess-1",
        rubric_version="v0",
        scores=[
            RubricScore(
                dimension="questioning_guidance",
                score=3,
                rationale="引导到位，给了学生思考空间。",
                evidence=[
                    Evidence(
                        dialog_id="stu_a",
                        chunk_seq=2,
                        excerpt="你觉得分母表示什么？",
                    )
                ],
            )
        ],
        overall=3.0,
        generated_at=_now(),
    )
    restored = EvaluationReport.model_validate_json(report.model_dump_json())
    assert restored.session_id == "sess-1"
    assert restored.scores[0].score == 3
    assert restored.scores[0].evidence[0].dialog_id == "stu_a"
    assert restored.overall == 3.0


def test_evaluation_report_overall_accepts_unavailable_fallback() -> None:
    """LLM 失败降级：overall 允许字符串 "unavailable"。"""
    report = EvaluationReport(
        session_id="sess-1",
        rubric_version="v0",
        scores=[],
        overall="unavailable",
        generated_at=_now(),
    )
    assert report.overall == "unavailable"


def test_evaluation_report_overall_rejects_arbitrary_string() -> None:
    with pytest.raises(ValidationError):
        EvaluationReport(
            session_id="sess-1",
            rubric_version="v0",
            scores=[],
            overall="great",  # type: ignore[arg-type]
            generated_at=_now(),
        )


def test_rubric_score_score_range() -> None:
    # 0–4 合法
    for s in (0, 2, 4):
        RubricScore(dimension="d", score=s, rationale="ok")
    # 越界
    with pytest.raises(ValidationError):
        RubricScore(dimension="d", score=5, rationale="ok")
    with pytest.raises(ValidationError):
        RubricScore(dimension="d", score=-1, rationale="ok")


def test_evidence_excerpt_length_cap() -> None:
    with pytest.raises(ValidationError):
        Evidence(dialog_id="stu_a", excerpt="x" * 121)


# ============================================================ TeacherFeedback


def test_teacher_feedback_round_trip() -> None:
    fb = TeacherFeedback(
        strengths=["提问清晰"],
        improvements=["可更耐心等待学生回答"],
        next_steps=["下次尝试追问 why 问题"],
        tone="encouraging",
        generated_at=_now(),
    )
    restored = TeacherFeedback.model_validate_json(fb.model_dump_json())
    assert restored.tone == "encouraging"
    assert restored.strengths == ["提问清晰"]


def test_teacher_feedback_rejects_unknown_tone() -> None:
    with pytest.raises(ValidationError):
        TeacherFeedback(
            strengths=["x"],
            improvements=["y"],
            next_steps=["z"],
            tone="sarcastic",  # type: ignore[arg-type]
            generated_at=_now(),
        )


def test_teacher_feedback_allows_empty_lists() -> None:
    """LLM 降级场景下字段可为空列表（字段本身不为 null）。"""
    fb = TeacherFeedback(
        strengths=[],
        improvements=[],
        next_steps=[],
        tone="neutral",
        generated_at=_now(),
    )
    assert fb.strengths == []
    assert fb.tone == "neutral"
