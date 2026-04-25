"""DirectorAgent 相关的 Pydantic 模型。

包含多学生调度器的动作、决策、配置与课堂消息结构。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ActionType = Literal["raise_hand", "speak", "daydream", "silent"]
ActivityLevel = Literal["low", "medium", "high"]
DisciplineLevel = Literal["loose", "strict"]
MessageRole = Literal["teacher", "student", "system"]


class Message(BaseModel):
    """课堂历史消息。"""

    speaker_id: str | None = Field(default=None, description="发言者标识")
    role: MessageRole = Field(..., description="消息角色：teacher/student/system")
    content: str = Field(..., description="消息内容")
    timestamp_seconds: int | None = Field(default=None, description="发生时间（秒）")


class StudentAction(BaseModel):
    """DirectorAgent 选出的单个学生动作。"""

    speaker_id: str = Field(..., description="学生标识")
    action_type: ActionType = Field(..., description="动作类型")
    priority: int = Field(..., ge=1, le=5, description="优先级，1-5")


class DirectorDecision(BaseModel):
    """DirectorAgent 的多学生调度决策。"""

    actions: list[StudentAction] = Field(default_factory=list, description="本轮学生动作")
    next_action_delay_ms: int = Field(..., description="下一次动作延迟（毫秒）")
    rationale: str = Field(..., description="决策理由")


class DirectorConfig(BaseModel):
    """DirectorAgent 可配置参数。"""

    min_students: int = Field(default=3, ge=3, le=8, description="最少学生数")
    max_students: int = Field(default=8, ge=3, le=8, description="最多学生数")
    activity_level: ActivityLevel = Field(default="medium", description="班级活跃度")
    discipline_level: DisciplineLevel = Field(default="strict", description="班级纪律性")
    speaker_cooldown_seconds: int = Field(default=20, ge=0, description="单学生发言冷却秒数")
    max_speaks_per_student: int = Field(default=3, ge=1, description="单学生软发言配额")
    max_actions_per_turn: int = Field(default=2, ge=1, description="每轮最多动作数")
    min_delay_ms: int = Field(default=800, ge=0, description="最小动作延迟")
    max_delay_ms: int = Field(default=6000, ge=0, description="最大动作延迟")
    seed: int | None = Field(default=None, description="可选随机种子")

    @model_validator(mode="after")
    def validate_ranges(self) -> "DirectorConfig":
        """校验配置区间的内部一致性。"""
        if self.min_students > self.max_students:
            raise ValueError("min_students must be <= max_students")
        if self.min_delay_ms > self.max_delay_ms:
            raise ValueError("min_delay_ms must be <= max_delay_ms")
        return self
