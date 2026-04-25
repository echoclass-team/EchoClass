"""DialogSession 模型 — 1v1 答疑陪练的对话会话。

每个 ``DialogSession`` 对应一个 ``StudentQuestion``：师范生与某个学生 Agent 在
多轮对话中尝试"解决"该问题。会话有明确的状态流转：

    pending → active → resolved | abandoned

resolution_source 记录"是怎么解决的"，便于事后区分"师范生真破除"和
"学生自我宣称懂了"。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.question import StudentQuestion

DialogStatus = Literal["pending", "active", "resolved", "abandoned"]
"""会话状态：

- ``pending``：问题已生成、尚未开启对话
- ``active``：师范生已点开此问题，对话进行中
- ``resolved``：问题已解决（成功）
- ``abandoned``：师范生主动放弃 / 切换到其他学生且未恢复
"""

ResolutionSource = Literal[
    "self_resolve",  # 学生在回复中宣称"懂了"，并经师范生确认
    "teacher_marked",  # 师范生手动点"已解答"按钮
    "auto_evaluator",  # 评估 Agent 自动判定（v2 才会有）
    "abandoned",  # 师范生放弃
]


class DialogMessage(BaseModel):
    """单条对话消息。"""

    role: Literal["teacher", "student"] = Field(..., description="说话者角色")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(..., description="发生时间")


class DialogSession(BaseModel):
    """一个 1v1 答疑会话。"""

    id: str = Field(..., description="会话唯一标识（UUID）")
    student_id: str = Field(..., description="学生 id")
    question: StudentQuestion = Field(..., description="本会话要解决的问题")
    status: DialogStatus = Field(default="pending", description="当前状态")
    messages: list[DialogMessage] = Field(
        default_factory=list,
        description="完整对话历史（不含学生提问本身——question 已是入口）",
    )
    started_at: datetime | None = Field(
        default=None, description="开启时间（status 进入 active 时设）"
    )
    ended_at: datetime | None = Field(
        default=None, description="结束时间（resolved/abandoned 时设）"
    )
    resolution_source: ResolutionSource | None = Field(
        default=None,
        description="结束方式；status=resolved/abandoned 时必填",
    )

    def turn_count(self) -> int:
        """对话轮数（一来一回算一轮，向上取整）。"""
        return (len(self.messages) + 1) // 2


class DialogReplyResult(BaseModel):
    """``StudentAgent.respond_in_dialog`` 的结构化返回。

    将 LLM 的纯文本输出 + ``[懂了]`` 标记拆解为结构化字段，便于上游 orchestrator
    决定是否触发"自我宣称解决"流程。
    """

    content: str = Field(..., description="去除标记后的学生回复正文")
    self_resolved: bool = Field(
        default=False,
        description="LLM 是否在末尾输出了 [懂了] 标记，表示学生认为问题已解决",
    )
    raw: str = Field(default="", description="LLM 原始输出（含可能的标记），便于排错")
