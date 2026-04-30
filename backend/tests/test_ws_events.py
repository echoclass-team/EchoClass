"""WS 协议事件模型单元测试 (#71)。

覆盖：
- 客户端事件 discriminated union 解码
- 服务端事件 discriminated union 解码
- 嵌入对象 (LessonMeta / StudentQuestion) 的序列化往返
- 错误码枚举受控
- 必填字段缺失时校验失败
- seq / chunk_seq 非负约束
"""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from schemas.ws_events import (
    WsAbandon,
    WsClientEvent,
    WsDialogActive,
    WsDialogAbandoned,
    WsDialogResolved,
    WsError,
    WsReplyChunk,
    WsReplyEnd,
    WsResolve,
    WsSelectDialog,
    WsServerEvent,
    WsSessionInit,
    WsStudentInfo,
    WsStudentNewQuestion,
    WsSummary,
    WsTeacherMessage,
)


_client_adapter: TypeAdapter[WsClientEvent] = TypeAdapter(WsClientEvent)
_server_adapter: TypeAdapter[WsServerEvent] = TypeAdapter(WsServerEvent)


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


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=["理解分数含义"],
        key_points=["理解几分之一的含义"],
        difficult_points=["分子分母关系"],
    )


# ============================================================ 客户端事件


def test_select_dialog_roundtrip() -> None:
    raw = json.dumps({"type": "select_dialog", "dialog_id": "q-1"})
    evt = _client_adapter.validate_json(raw)
    assert isinstance(evt, WsSelectDialog)
    assert evt.dialog_id == "q-1"


def test_teacher_message_requires_text() -> None:
    raw = json.dumps(
        {"type": "teacher_message", "dialog_id": "q-1", "text": "你说说看"}
    )
    evt = _client_adapter.validate_json(raw)
    assert isinstance(evt, WsTeacherMessage)
    assert evt.text == "你说说看"

    # 空 text 应被拒
    with pytest.raises(ValidationError):
        _client_adapter.validate_json(
            json.dumps({"type": "teacher_message", "dialog_id": "q-1", "text": ""})
        )


def test_resolve_default_source() -> None:
    raw = json.dumps({"type": "resolve", "dialog_id": "q-1"})
    evt = _client_adapter.validate_json(raw)
    assert isinstance(evt, WsResolve)
    assert evt.source == "teacher_marked"  # 默认值


def test_resolve_self_resolve_source() -> None:
    raw = json.dumps({"type": "resolve", "dialog_id": "q-1", "source": "self_resolve"})
    evt = _client_adapter.validate_json(raw)
    assert isinstance(evt, WsResolve)
    assert evt.source == "self_resolve"


def test_abandon_event() -> None:
    raw = json.dumps({"type": "abandon", "dialog_id": "q-1"})
    evt = _client_adapter.validate_json(raw)
    assert isinstance(evt, WsAbandon)


def test_unknown_client_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _client_adapter.validate_json(
            json.dumps({"type": "what_is_this", "dialog_id": "q-1"})
        )


# ============================================================ 服务端事件


def test_session_init_with_embedded_lesson_and_questions() -> None:
    init = WsSessionInit(
        seq=0,
        session_id="sess-1",
        lesson=_lesson(),
        students=[
            WsStudentInfo(
                id="p1",
                name="小明",
                stage_id="p_middle",
                subject_level="中等",
                summary="活泼好动",
            )
        ],
        questions=[_question()],
    )
    # JSON 往返
    payload = init.model_dump_json()
    decoded = _server_adapter.validate_json(payload)
    assert isinstance(decoded, WsSessionInit)
    assert decoded.lesson.topic == "分数的初步认识"
    assert decoded.questions[0].category == "clarify_concept"
    assert decoded.students[0].name == "小明"
    assert decoded.seq == 0


def test_reply_chunk_chunk_seq_required_non_negative() -> None:
    chunk = WsReplyChunk(seq=3, dialog_id="q-1", delta="哦", chunk_seq=0)
    decoded = _server_adapter.validate_json(chunk.model_dump_json())
    assert isinstance(decoded, WsReplyChunk)
    assert decoded.chunk_seq == 0

    with pytest.raises(ValidationError):
        WsReplyChunk(seq=3, dialog_id="q-1", delta="哦", chunk_seq=-1)


def test_reply_end_with_self_resolved_flag() -> None:
    end = WsReplyEnd(
        seq=10,
        dialog_id="q-1",
        full_content="哦！我懂了。",
        self_resolved=True,
    )
    decoded = _server_adapter.validate_json(end.model_dump_json())
    assert isinstance(decoded, WsReplyEnd)
    assert decoded.self_resolved is True


def test_dialog_active_resolved_abandoned() -> None:
    for evt_cls, payload in (
        (WsDialogActive, {"type": "dialog_active", "seq": 1, "dialog_id": "q-1"}),
        (
            WsDialogResolved,
            {
                "type": "dialog_resolved",
                "seq": 2,
                "dialog_id": "q-1",
                "source": "self_resolve",
            },
        ),
        (
            WsDialogAbandoned,
            {"type": "dialog_abandoned", "seq": 3, "dialog_id": "q-1"},
        ),
    ):
        decoded = _server_adapter.validate_json(json.dumps(payload))
        assert isinstance(decoded, evt_cls), (
            f"expected {evt_cls.__name__}, got {type(decoded)}"
        )


def test_summary_event_carries_dict() -> None:
    summary_data = {
        "session_id": "sess-1",
        "total_questions": 6,
        "resolved": 4,
        "abandoned": 1,
    }
    decoded = _server_adapter.validate_json(
        json.dumps({"type": "summary", "seq": 99, "data": summary_data})
    )
    assert isinstance(decoded, WsSummary)
    assert decoded.data["resolved"] == 4


def test_error_event_with_known_code() -> None:
    decoded = _server_adapter.validate_json(
        json.dumps(
            {
                "type": "error",
                "seq": 5,
                "code": "dialog_not_found",
                "message": "dialog q-9 not found",
            }
        )
    )
    assert isinstance(decoded, WsError)
    assert decoded.code == "dialog_not_found"
    assert decoded.dialog_id is None


def test_error_event_unknown_code_rejected() -> None:
    """code 是受控枚举，未知值必须被拒。"""
    with pytest.raises(ValidationError):
        _server_adapter.validate_json(
            json.dumps(
                {
                    "type": "error",
                    "seq": 5,
                    "code": "what_is_this",
                    "message": "...",
                }
            )
        )


def test_server_event_seq_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        WsDialogActive(seq=-1, dialog_id="q-1")


def test_server_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _server_adapter.validate_json(
            json.dumps({"type": "made_up", "seq": 0, "foo": "bar"})
        )


# ============================================== M3 student_new_question (#111)


def test_student_new_question_roundtrip() -> None:
    """学生主动追问帧 JSON 往返：question 嵌入对象、字段完整保留。"""
    evt = WsStudentNewQuestion(
        seq=42,
        dialog_id="stu_a",
        question=_question(),
        after_reply_chunk_seq=3,
    )
    decoded = _server_adapter.validate_json(evt.model_dump_json())
    assert isinstance(decoded, WsStudentNewQuestion)
    assert decoded.dialog_id == "stu_a"
    assert decoded.question.id == "q-1"
    assert decoded.question.category == "clarify_concept"
    assert decoded.after_reply_chunk_seq == 3
    assert decoded.seq == 42


def test_student_new_question_after_reply_chunk_seq_optional() -> None:
    """after_reply_chunk_seq 缺省 -> None；首问场景使用。"""
    evt = WsStudentNewQuestion(
        seq=0,
        dialog_id="stu_a",
        question=_question(),
    )
    assert evt.after_reply_chunk_seq is None
    decoded = _server_adapter.validate_json(evt.model_dump_json())
    assert isinstance(decoded, WsStudentNewQuestion)
    assert decoded.after_reply_chunk_seq is None


def test_student_new_question_negative_chunk_seq_rejected() -> None:
    """after_reply_chunk_seq 必须非负（与 reply_chunk.chunk_seq 对齐）。"""
    with pytest.raises(ValidationError):
        WsStudentNewQuestion(
            seq=0,
            dialog_id="stu_a",
            question=_question(),
            after_reply_chunk_seq=-1,
        )


def test_student_new_question_in_server_union_dispatches_correctly() -> None:
    """通过 type 字段从服务端 union 正确分发到 WsStudentNewQuestion。"""
    payload = {
        "type": "student_new_question",
        "seq": 7,
        "dialog_id": "stu_b",
        "question": _question().model_dump(mode="json"),
    }
    decoded = _server_adapter.validate_json(json.dumps(payload))
    assert isinstance(decoded, WsStudentNewQuestion)
    # 不会被误匹配到 WsReplyEnd 等其他帧
    assert decoded.type == "student_new_question"
