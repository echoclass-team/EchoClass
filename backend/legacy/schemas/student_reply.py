"""Legacy StudentReply / Intent — 旧回合制 Student Agent 的结构化输出。

转型后（详见 ``docs/PIVOT.md``）新 1v1 答疑陪练用 ``schemas.dialog.DialogReplyResult``
作为对话回复模型，本模块**仅供 legacy 模块内部 import**，新代码请勿使用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["answer_question", "ask_question", "off_topic", "passive"]


class StudentReply(BaseModel):
    """旧 ``StudentAgent.respond()`` 的结构化输出。"""

    speaker_id: str = Field(..., description="学生标识")
    intent: Intent = Field(..., description="回复意图")
    content: str = Field(..., description="回复文本")
    emotion: str = Field(..., description="当前情绪，如'困惑'、'自信'、'无聊'")
    triggered_misconception_id: str | None = Field(
        default=None,
        description="本轮触发的学科迷思 id；无触发时为空",
    )
