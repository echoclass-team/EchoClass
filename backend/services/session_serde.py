"""QASession 序列化 / 反序列化 helper（M3-A5 #126 / M3-A7 #128 共享）。

设计目标
--------
把一次 ``QASession`` 的纯数据态（lesson_meta + dialogs）连同可选的
``EvaluationReport`` / ``TeacherFeedback`` 一同写入 / 读出 JSON，以服务两类
脚本：

- ``scripts/replay_eval.py``（#M3-A5）：从 JSON 重建 session 后重新跑 evaluator
- ``scripts/seed_demo.py``（#M3-A7）：把 demo 三份样本灌入 DB

序列化规范
----------
JSON 顶层结构::

    {
      "version": 1,
      "label": "good" | "mid" | "bad" | <自定义>,
      "session": {
        "id": "...",
        "lesson_meta": {...LessonMeta...},
        "persona_ids": ["p_lower_curious", ...],   # 可选，用于 DB 灌入
        "dialogs": [
          {...DialogSession.model_dump()...},
          ...
        ]
      },
      "evaluation": {...EvaluationReport...} | null,
      "feedback":   {...TeacherFeedback...}   | null
    }

不变式
------
- 反序列化得到的 ``QASession`` 不含 ``StudentAgent``（``_agents`` 为空）；
  仅可用于 ``EvaluatorAgent`` / ``FeedbackAgent`` 等只读消费方。
- ``persona_ids`` 仅做元信息（DB 灌入需要），不参与 evaluator 输入。
- 字段缺失走 Pydantic 默认值；增量字段不破坏旧 JSON。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.dialog import DialogSession
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta
from services.qa_session import QASession

CURRENT_VERSION = 1


@dataclass
class SessionBundle:
    """一份序列化 session 的完整内容（session + 可选评估/反馈）。"""

    session: QASession
    evaluation: EvaluationReport | None = None
    feedback: TeacherFeedback | None = None
    label: str | None = None
    persona_ids: list[str] | None = None


# ============================================================ dump


def dump_bundle_to_dict(bundle: SessionBundle) -> dict[str, Any]:
    """把 ``SessionBundle`` 序列化为可直接 ``json.dumps`` 的 dict。

    与 ``load_bundle_from_dict`` 一一对应；新增字段时同步更新两侧。
    """
    session = bundle.session
    payload: dict[str, Any] = {
        "version": CURRENT_VERSION,
        "label": bundle.label,
        "session": {
            "id": session.id,
            "lesson_meta": session.lesson_meta.model_dump(mode="json"),
            "persona_ids": list(bundle.persona_ids or []),
            "dialogs": [
                dialog.model_dump(mode="json")
                for dialog in session.dialogs.values()
            ],
        },
        "evaluation": (
            bundle.evaluation.model_dump(mode="json")
            if bundle.evaluation is not None
            else None
        ),
        "feedback": (
            bundle.feedback.model_dump(mode="json")
            if bundle.feedback is not None
            else None
        ),
    }
    return payload


# ============================================================ load


def load_bundle_from_dict(data: dict[str, Any]) -> SessionBundle:
    """从 dict 重建 ``SessionBundle``。

    反序列化得到的 ``QASession`` 仅含 ``id`` / ``lesson_meta`` / ``dialogs``；
    ``_agents`` 为空（没有真实的 StudentAgent）。够 EvaluatorAgent / FeedbackAgent
    跑评估 + 反馈。
    """
    version = data.get("version")
    if version != CURRENT_VERSION:
        raise ValueError(
            f"unsupported session bundle version: {version!r} "
            f"(expected {CURRENT_VERSION})"
        )

    session_payload = data.get("session") or {}
    lesson_meta = LessonMeta.model_validate(session_payload["lesson_meta"])
    session = QASession(
        lesson_meta=lesson_meta,
        session_id=session_payload["id"],
    )
    for dialog_payload in session_payload.get("dialogs", []):
        dialog = DialogSession.model_validate(dialog_payload)
        session.dialogs[dialog.id] = dialog

    evaluation: EvaluationReport | None = None
    eval_payload = data.get("evaluation")
    if eval_payload is not None:
        evaluation = EvaluationReport.model_validate(eval_payload)

    feedback: TeacherFeedback | None = None
    feedback_payload = data.get("feedback")
    if feedback_payload is not None:
        feedback = TeacherFeedback.model_validate(feedback_payload)

    persona_ids = list(session_payload.get("persona_ids") or [])

    return SessionBundle(
        session=session,
        evaluation=evaluation,
        feedback=feedback,
        label=data.get("label"),
        persona_ids=persona_ids,
    )


__all__ = [
    "CURRENT_VERSION",
    "SessionBundle",
    "dump_bundle_to_dict",
    "load_bundle_from_dict",
]
