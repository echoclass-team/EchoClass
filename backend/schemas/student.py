"""Student agent response schema."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["answer_question", "ask_question", "off_topic", "passive"]


class Persona(BaseModel):
    """学生人设描述。"""

    name: str = Field(..., description="学生姓名")
    personality: str = Field(..., description="性格特征，如'内向害羞'、'活泼好动'")
    knowledge_level: str = Field(
        ..., description="知识水平，如'基础薄弱'、'中等水平'、'优等生'"
    )
    behavior_traits: str = Field(
        ..., description="课堂行为倾向，如'容易走神'、'积极举手'、'沉默寡言'"
    )


class ClassroomContext(BaseModel):
    """当前课堂上下文。"""

    subject: str = Field(..., description="科目，如'数学'")
    topic: str = Field(..., description="当前话题，如'分数的概念'")
    history: list[str] = Field(
        default_factory=list,
        description="之前的课堂对话摘要",
    )


class StudentReply(BaseModel):
    """StudentAgent 的结构化输出。"""

    speaker_id: str = Field(..., description="学生标识")
    intent: Intent = Field(..., description="回复意图")
    content: str = Field(..., description="回复文本")
    emotion: str = Field(..., description="当前情绪，如'困惑'、'自信'、'无聊'")
