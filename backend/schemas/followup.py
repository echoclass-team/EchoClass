"""``StudentAgent.decide_followup`` 的请求 / 返回模型 (#A2 / #111)。

M3 连续答疑模式下，每轮老师消息 → 学生回复完成后，由 LLM 决策学生是否
应该主动追问；若是，生成新的 ``StudentQuestion``。

设计要点
--------

- ``should_followup=False`` 时 ``new_question`` 必须为 ``None``
- ``should_followup=True`` 时 ``new_question`` 必须非空（解析失败 → 降级为 False）
- ``reason`` 始终保留 LLM 给出的决策理由，便于排错与 EvaluatorAgent 引用
- LLM 输出格式异常 / Schema 不合法时调用方应**降级返回** ``no_followup``，不抛出
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from schemas.question import StudentQuestion


class FollowupDecision(BaseModel):
    """学生是否主动追问的决策结果。"""

    should_followup: bool = Field(
        ..., description="是否应该主动抛新问题（True = 追问，False = 沉默）"
    )
    new_question: StudentQuestion | None = Field(
        default=None,
        description=(
            "should_followup=True 时为新生成的问题（含 id / speaker_* 等完整字段）；"
            "should_followup=False 时必须为 None"
        ),
    )
    reason: str = Field(
        default="",
        description="LLM 给出的决策理由，便于排错与后续 evaluator 引用",
    )

    @model_validator(mode="after")
    def _check_question_consistency(self) -> "FollowupDecision":
        """``should_followup`` 与 ``new_question`` 的存在性必须一致。"""
        if self.should_followup and self.new_question is None:
            raise ValueError(
                "should_followup=True 时 new_question 不能为 None"
            )
        if not self.should_followup and self.new_question is not None:
            raise ValueError(
                "should_followup=False 时 new_question 必须为 None"
            )
        return self

    @classmethod
    def no_followup(cls, reason: str = "") -> "FollowupDecision":
        """构造"不追问"的决策（解析失败 / 边界情况降级用）。"""
        return cls(should_followup=False, new_question=None, reason=reason)


__all__ = ["FollowupDecision"]
