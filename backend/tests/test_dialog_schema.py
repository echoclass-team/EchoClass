"""DialogMessage / DialogSession schema 单元测试 (#111)。

覆盖 M3 连续答疑模式下的新增字段：

- ``DialogMessage.is_new_question`` 默认 False、显式赋值往返
- ``DialogMessage.question_id`` 默认 None、显式赋值往返
- 旧消息（仅 v1 字段）反序列化兼容
- ``DialogSession.messages`` 嵌入新字段消息后仍可正常 dump/load
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.dialog import DialogMessage, DialogSession
from schemas.question import StudentQuestion


def _now() -> datetime:
    return datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


def _question() -> StudentQuestion:
    return StudentQuestion(
        id="q-1",
        speaker_id="p1",
        speaker_name="小明",
        content="老师，几分之一的'几'是什么意思？",
        category="clarify_concept",
        difficulty="easy",
        linked_key_point="理解几分之一的含义",
        rationale="分子分母分不清。",
    )


# ============================================ DialogMessage 默认值（向后兼容）


def test_dialog_message_defaults_for_v1_compat() -> None:
    """M2 闯关模式下，新字段必须有默认值，旧调用方不受影响。"""
    msg = DialogMessage(role="teacher", content="你说说看", timestamp=_now())
    assert msg.self_resolved is False
    assert msg.is_new_question is False
    assert msg.question_id is None


def test_dialog_message_legacy_payload_deserialization() -> None:
    """从只含 v1 字段的 JSON 还能正确反序列化（前端旧 payload 兼容）。"""
    raw = {
        "role": "student",
        "content": "嗯",
        "timestamp": "2026-04-28T12:00:00+00:00",
        "self_resolved": False,
    }
    msg = DialogMessage.model_validate(raw)
    assert msg.is_new_question is False
    assert msg.question_id is None


# ============================================ DialogMessage M3 新字段语义


def test_dialog_message_is_new_question_explicit() -> None:
    """学生主动追问的回合：is_new_question=True + question_id 关联新题。"""
    msg = DialogMessage(
        role="student",
        content="老师，那分子又是什么？",
        timestamp=_now(),
        is_new_question=True,
        question_id="q-2",
    )
    dumped = msg.model_dump(mode="json")
    assert dumped["is_new_question"] is True
    assert dumped["question_id"] == "q-2"

    # JSON 往返
    restored = DialogMessage.model_validate(dumped)
    assert restored.is_new_question is True
    assert restored.question_id == "q-2"


def test_dialog_message_question_id_can_be_set_without_new_question_flag() -> None:
    """普通回合也可以带 question_id（如老师对当前 question 的解释）。"""
    msg = DialogMessage(
        role="teacher",
        content="分子代表分到了几份。",
        timestamp=_now(),
        question_id="q-2",
    )
    assert msg.is_new_question is False
    assert msg.question_id == "q-2"


def test_dialog_message_self_resolved_and_new_question_independence() -> None:
    """self_resolved 与 is_new_question 是独立字段，可同时存在。

    场景：学生回答完老师上一题后，自己说了 [懂了] 同时又抛新问题——边界但允许。
    """
    msg = DialogMessage(
        role="student",
        content="哦哦懂了，那老师我还想问……",
        timestamp=_now(),
        self_resolved=True,
        is_new_question=True,
        question_id="q-3",
    )
    assert msg.self_resolved is True
    assert msg.is_new_question is True


def test_dialog_message_rejects_unknown_role() -> None:
    """role 仍是受控枚举，未知角色被拒（防回归）。"""
    with pytest.raises(ValidationError):
        DialogMessage.model_validate(
            {
                "role": "system",
                "content": "x",
                "timestamp": "2026-04-28T12:00:00+00:00",
            }
        )


# ============================================ DialogSession 内嵌新字段


def test_dialog_session_with_mixed_messages_roundtrip() -> None:
    """DialogSession 内 messages 含 v1 + v2 字段混合，能完整 dump/load。"""
    session = DialogSession(
        id="sess-1",
        student_id="stu_a",
        question=_question(),
        status="active",
        messages=[
            DialogMessage(
                role="teacher",
                content="说说看",
                timestamp=_now(),
            ),
            DialogMessage(
                role="student",
                content="嗯……我觉得分母是下面那个数",
                timestamp=_now(),
                self_resolved=False,
                question_id="q-1",
            ),
            DialogMessage(
                role="student",
                content="老师，那分子是什么？",
                timestamp=_now(),
                is_new_question=True,
                question_id="q-2",
            ),
        ],
    )

    dumped = session.model_dump_json()
    restored = DialogSession.model_validate_json(dumped)

    assert len(restored.messages) == 3
    assert restored.messages[0].is_new_question is False
    assert restored.messages[0].question_id is None
    assert restored.messages[1].question_id == "q-1"
    assert restored.messages[1].is_new_question is False
    assert restored.messages[2].is_new_question is True
    assert restored.messages[2].question_id == "q-2"
