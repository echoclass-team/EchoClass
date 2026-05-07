"""``agents.evaluator`` 单元测试 (#M3-A1 / #123)。

仅覆盖骨架 + mock 行为，不调真实 LLM。
真实 LLM 路径（``llm 非空``）仅断言抛 ``NotImplementedError``，等 #M3-A3 替换。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.evaluator import (
    RUBRIC_DIR,
    EvaluatorAgent,
    build_dialog_projection,
    load_rubric,
)
from schemas.dialog import DialogMessage, DialogSession, QuestionProgress
from schemas.evaluation import EvaluationReport
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from services.qa_session import QASession


# ============================================================ helpers


def _fake_session(session_id: str = "sess-test") -> QASession:
    lesson = LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=["理解分数含义"],
        key_points=["分数的定义"],
        difficult_points=["平均分的理解"],
    )
    return QASession(lesson_meta=lesson, session_id=session_id)


def _fake_question(question_id: str, content: str) -> StudentQuestion:
    return StudentQuestion(
        id=question_id,
        speaker_id="s1",
        speaker_name="小明",
        content=content,
        category="clarify_concept",
        difficulty="easy",
        rationale="",
    )


def _message(role: str, content: str, **kwargs) -> DialogMessage:
    return DialogMessage(
        role=role,
        content=content,
        timestamp=datetime.now().astimezone(),
        **kwargs,
    )


# ============================================================ load_rubric


def test_load_rubric_v0_has_expected_shape() -> None:
    rubric = load_rubric("v0")
    assert rubric["version"] == "v0"
    assert isinstance(rubric["dimensions"], list)
    assert len(rubric["dimensions"]) >= 1
    # 每个维度至少有 id + levels
    for dim in rubric["dimensions"]:
        assert "id" in dim
        assert "levels" in dim


def test_load_rubric_v0_matches_disk() -> None:
    """直接读 JSON 与 ``load_rubric`` 返回应一致（防 helper 偷偷转换字段）。"""
    raw = json.loads((RUBRIC_DIR / "v0.json").read_text(encoding="utf-8"))
    assert load_rubric("v0") == raw


def test_load_rubric_unknown_version_raises() -> None:
    with pytest.raises(FileNotFoundError, match="Rubric not found"):
        load_rubric("v999")


# ============================================================ dialog projection


def test_build_dialog_projection_segments_m3_questions_by_progress() -> None:
    session = _fake_session()
    q1 = _fake_question("s1", "分母是什么意思？")
    q2 = _fake_question("s1-q2", "分子是什么意思？")
    dialog = DialogSession(
        id="s1",
        student_id="s1",
        question=q1,
        status="active",
        messages=[
            _message("teacher", "先看分母"),
            _message("student", "分母是下面的数"),
            _message(
                "student",
                "分子是什么意思？",
                is_new_question=True,
                question_id="s1-q2",
            ),
            _message("teacher", "再看上面的数"),
            _message("student", "分子表示取了几份", self_resolved=True),
        ],
        asked_questions=[q1, q2],
        question_progress=[
            QuestionProgress(
                question_id="s1",
                status="resolved",
                turns_used=1,
                message_start_idx=0,
                message_end_idx=2,
                resolution_source="teacher_marked",
            ),
            QuestionProgress(
                question_id="s1-q2",
                status="active",
                turns_used=1,
                message_start_idx=2,
            ),
        ],
        current_question_idx=1,
    )
    session.dialogs[dialog.id] = dialog

    projection = build_dialog_projection(session)

    assert len(projection) == 1
    projected_dialog = projection[0]
    assert projected_dialog["dialog_id"] == "s1"
    assert [q["question_id"] for q in projected_dialog["questions"]] == ["s1", "s1-q2"]
    assert [m["message_idx"] for m in projected_dialog["questions"][0]["messages"]] == [
        0,
        1,
    ]
    assert [m["message_idx"] for m in projected_dialog["questions"][1]["messages"]] == [
        2,
        3,
        4,
    ]
    assert projected_dialog["questions"][0]["resolution_source"] == "teacher_marked"
    assert projected_dialog["questions"][1]["messages"][0]["is_new_question"] is True
    assert projected_dialog["questions"][1]["messages"][0]["question_id"] == "s1-q2"


def test_build_dialog_projection_falls_back_without_progress() -> None:
    session = _fake_session()
    q1 = _fake_question("legacy-q1", "什么是分数？")
    dialog = DialogSession(
        id="legacy-q1",
        student_id="s1",
        question=q1,
        status="resolved",
        messages=[
            _message("teacher", "你哪里不懂？"),
            _message("student", "我不懂平均分", self_resolved=True),
        ],
        resolution_source="self_resolve",
    )
    session.dialogs[dialog.id] = dialog

    projection = build_dialog_projection(session)

    questions = projection[0]["questions"]
    assert len(questions) == 1
    assert questions[0]["question_id"] == "legacy-q1"
    assert questions[0]["resolution_source"] == "self_resolve"
    assert [m["message_idx"] for m in questions[0]["messages"]] == [0, 1]


# ============================================================ mock evaluate


async def test_mock_evaluate_returns_one_score_per_dimension() -> None:
    evaluator = EvaluatorAgent()  # llm=None → mock
    session = _fake_session()

    report = await evaluator.evaluate(session)

    assert isinstance(report, EvaluationReport)
    assert report.session_id == session.id
    assert report.rubric_version == "v0"
    # 每维度一条 score
    rubric_dim_ids = [d["id"] for d in evaluator.rubric["dimensions"]]
    assert [s.dimension for s in report.scores] == rubric_dim_ids


async def test_mock_evaluate_uses_placeholder_score() -> None:
    """mock 实现必须明确给出可识别的占位（避免被误当真实评分）。"""
    report = await EvaluatorAgent().evaluate(_fake_session())
    for score in report.scores:
        assert 0 <= score.score <= 4
        assert "[mock]" in score.rationale
        assert score.evidence == []
    assert report.overall == 3.0


async def test_mock_evaluate_generated_at_is_recent() -> None:
    before = datetime.now().astimezone()
    report = await EvaluatorAgent().evaluate(_fake_session())
    after = datetime.now().astimezone()
    assert before <= report.generated_at.astimezone() <= after


async def test_mock_report_is_json_serializable_for_b3() -> None:
    """B3 / B4 通过 ``model_dump_json`` 消费报告；保证可序列化往返。"""
    report = await EvaluatorAgent().evaluate(_fake_session())
    payload = report.model_dump_json()
    restored = EvaluationReport.model_validate_json(payload)
    assert restored.session_id == report.session_id
    assert len(restored.scores) == len(report.scores)


# ============================================================ real path stub


async def test_real_evaluate_not_implemented_yet() -> None:
    """传入 LLMClient 的真实路径应在 #M3-A3 实现前明确抛错。"""
    fake_llm = MagicMock()  # 不会被调用，只用于触发 real 路径分支
    evaluator = EvaluatorAgent(llm=fake_llm)

    with pytest.raises(NotImplementedError, match="#M3-A3"):
        await evaluator.evaluate(_fake_session())


# ============================================================ rubric_version


async def test_rubric_version_propagates_to_report() -> None:
    evaluator = EvaluatorAgent(rubric_version="v0")
    report = await evaluator.evaluate(_fake_session())
    assert report.rubric_version == "v0"


def test_unknown_rubric_version_raises_at_construct_time() -> None:
    """版本错误在构造时立刻抛，不要拖到 evaluate。"""
    with pytest.raises(FileNotFoundError):
        EvaluatorAgent(rubric_version="v999")


# ============================================================ prompt file


def test_evaluator_prompt_template_exists() -> None:
    """``prompts/evaluator.j2`` 存在；#M3-A3 真实实现会读它。"""
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "evaluator.j2"
    assert prompt_path.exists()
    assert prompt_path.stat().st_size > 0
