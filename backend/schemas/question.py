"""StudentQuestion 模型 — 学生主动提问。

`StudentAgent.generate_questions(lesson_meta)` 的输出单元，也是 1v1 答疑陪练的
入口对象：每个 question 关联一个 dialog session，师范生需要在多轮对话内"解决"
该 question。

设计要点：
- ``category`` 显式区分提问类型，便于前端 UI 上图标化、统计与评估
- ``difficulty`` 标记难度，便于按难度梯度推送问题
- ``linked_key_point`` / ``linked_misconception_id`` 把问题挂回到教案与迷思库，
  让"是否破除迷思"评估有锚点
- ``rationale`` 是学生的"内心 OS"，仅供后端评估，不暴露给师范生
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

QuestionCategory = Literal[
    "clarify_concept",  # 澄清概念："老师，XXX 是什么意思？"
    "challenge_example",  # 反例挑战："那如果是 XXX 这种情况呢？"
    "extend_topic",  # 拓展联想："那这个跟 XXX 有什么关系？"
    "off_topic",  # 跑题："老师，下课能玩游戏吗？"
    "stuck_misconception",  # 卡在迷思："我觉得应该是 XXX，对吗？"（含错误前提）
]

QuestionDifficulty = Literal["easy", "medium", "hard"]


class StudentQuestion(BaseModel):
    """学生主动提出的一个问题。"""

    id: str = Field(..., description="问题唯一标识（UUID）")
    speaker_id: str = Field(..., description="提问学生 id（对应 Persona.id）")
    speaker_name: str = Field(..., description="提问学生姓名（用于前端展示）")
    content: str = Field(..., description="学生原话（自然语气，不要机器人腔）")
    category: QuestionCategory = Field(..., description="提问类型")
    difficulty: QuestionDifficulty = Field(..., description="难度等级")
    linked_key_point: str | None = Field(
        default=None,
        description="关联的教案重点（取自 LessonMeta.key_points），无明显关联可为空",
    )
    linked_misconception_id: str | None = Field(
        default=None,
        description="关联的迷思 id（取自 misconception 库），仅 stuck_misconception / challenge_example 类问题可能有",
    )
    rationale: str = Field(
        default="",
        description="学生内心 OS：为什么会这样问。仅供后端评估，不展示给师范生。",
    )
    self_score: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "二阶段 self-check 给本问题的综合评分（0-100）。"
            "由 ``StudentAgent`` 在生成后再调一次 LLM 自评得到，"
            "用于按质量排序与多样性筛选。未跑 self-check 时为 None。"
        ),
    )
