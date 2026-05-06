"""师范生反馈 schema — M3 协议冻结占位（Epic #121 / 真实实现 #M3-A2）。

与 ``docs/api_contract.md §2.6.3`` 保持一致。

**与 ``EvaluationReport`` 的区别**：

- ``EvaluationReport`` 面向 *评估* — 维度打分 + 证据，给评委 / 数据用
- ``TeacherFeedback`` 面向 *师范生成长* — 肯定 + 改进点 + 下一步建议，自然语言

两者同时由后端异步生成，由 ``GET /api/qa-sessions/{id}/evaluation`` 一同返回
（详见 api_contract §2.6.1）。

真实生成逻辑由 FeedbackAgent 在 #M3-A4 填充；schema 变更需 A+B 双 approve。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TeacherFeedback(BaseModel):
    """给师范生的结课反馈（由 FeedbackAgent 生成，面向用户可读）。"""

    strengths: list[str] = Field(
        default_factory=list,
        description="做得好的地方；强烈建议 ≥ 1 条，LLM 降级时可为占位语句但保持列表非空",
    )
    improvements: list[str] = Field(
        default_factory=list,
        description="具体可改进点；强烈建议 ≥ 1 条，内容应指向对话中的具体行为",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="下一步练习 / 学习建议；强烈建议 ≥ 1 条，可指向教材章节或特定技能点",
    )
    tone: Literal["encouraging", "neutral", "critical"] = Field(
        default="encouraging",
        description=(
            "反馈语气。前端据此决定图标 / 颜色提示。"
            "未来扩展新枚举值前必须开 PR 修改本字段 + api_contract §2.6.3。"
        ),
    )
    generated_at: datetime = Field(..., description="反馈生成时间（UTC）")


__all__ = ["TeacherFeedback"]
