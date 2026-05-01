"""DialogSession 模型 — 1v1 答疑陪练的对话会话。

会话有明确的状态流转::

    pending → active → resolved | abandoned

``resolution_source`` 记录"是怎么解决的"，便于事后区分"师范生真破除"和
"学生自我宣称懂了"。

形态演进
--------

**M2 闯关模式（v1，已上线）**
    每个 ``DialogSession`` 1:1 对应一个 ``StudentQuestion``：一个学生可能持有
    N 个 dialog（每题一个），师范生从队列里挑题进入 1v1。
    ``messages`` 内全部消息都属于 ``dialog.question`` 这一道题。

**M3 连续答疑模式（v2，规划中，issue #111）**
    每个 ``DialogSession`` 1:1 对应一个**学生**（``student_id``）：一个学生只
    有一个 dialog，``dialog.question`` 退化为"学生抛出的第一个问题"，后续
    问题由 ``StudentAgent.decide_followup`` 自主决定何时发出，以
    ``DialogMessage(role="student", is_new_question=True, question_id=...)``
    形式插入 ``messages``。``mark_resolved`` 语义升级为"结束整段辅导"。

两种形态在字段层完全兼容：
- v1 的 ``DialogMessage`` 永远 ``is_new_question=False`` / ``question_id=None``
- v2 引入新字段 + 新 WS 帧 ``student_new_question``（见 ``ws_events``）
- v2 给 ``DialogSession`` 加了 ``asked_questions`` 字段追踪首问 + 追问列表，
  M2 模式下仅含首问一项，向后兼容
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
    """单条对话消息。

    M3 连续答疑模式下，一个 dialog 内可能跨越多个 ``StudentQuestion``：
    学生主动追问的回合用 ``is_new_question=True`` 标识，``question_id`` 关联到
    新 question 的 id；老师与该 question 无关的过渡消息（如鼓励、点评）则
    保持默认值。
    """

    role: Literal["teacher", "student"] = Field(..., description="说话者角色")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(..., description="发生时间")
    self_resolved: bool = Field(
        default=False,
        description=(
            "仅 role='student' 时可能为 True：LLM 在本轮回复末尾输出了 [懂了] 标记。"
            "前端复原历史时据此渲染绿色提示条等 UI；teacher 回合永远 False。"
        ),
    )
    is_new_question: bool = Field(
        default=False,
        description=(
            "M3 连续答疑模式下，仅 role='student' 时可能为 True：本条消息是学生"
            "主动抛出的新问题（不是对老师上一句的回应）。前端据此渲染'新问题'气泡。"
            "M2 闯关模式下永远 False。"
        ),
    )
    question_id: str | None = Field(
        default=None,
        description=(
            "M3 连续答疑模式下，本条消息所属 question 的 id；用于评估时按问题分段。"
            "M2 闯关模式下永远 None（dialog 与 question 一一对应，无需冗余记录）。"
        ),
    )


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
    asked_questions: list[StudentQuestion] = Field(
        default_factory=list,
        description=(
            "M3 连续答疑模式下，学生在本 dialog 中抛出的所有问题：首问（==``question``）为第"
            "一项，后续由 ``StudentAgent.decide_followup`` 生成的追问依次追加。供决策层查重 / "
            "评估层按问题分段。M2 闯关模式下仅含首问一项。spawn 时赋初值=[question]。"
        ),
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


StudentStreamEventType = Literal["delta", "final", "followup"]
"""StudentAgent / QASession 流式事件的三种类型：

- ``delta``：增量文本片段，UI 应追加到当前学生气泡里。由 ``StudentAgent
  .stream_in_dialog`` 产生。
- ``final``：本轮学生回复结束，``result`` 是结构化的最终结果（含
  self_resolved）。由 ``StudentAgent.stream_in_dialog`` 产生。
- ``followup``（M3 / #111）：本轮回复后学生主动抛出的新问题。``new_question``
  非空。由 ``QASession.stream_teacher_message`` 在 ``final`` 之后可选追加（
  ``StudentAgent.decide_followup`` 决策 should_followup=True 时）。仅出现一次。
"""


class StudentStreamEvent(BaseModel):
    """学生流式事件（agent 层 + service 层共用类型）。

    序列中的位置与语义::

        delta * N → final → [followup]?

    使用方式（UI / WS endpoint）::

        async for evt in session.stream_teacher_message(...):
            if evt.type == "delta":
                ui.append(evt.delta)
            elif evt.type == "final":
                ui.replace(evt.result.content)
                if evt.result.self_resolved:
                    propose_resolve()
            elif evt.type == "followup":
                ui.append_new_question_bubble(evt.new_question)

    设计要点：
    - delta 不会包含末尾的 ``[懂了]`` 标记（agent 内部用 hold-back 缓冲过滤）
    - final.content 是权威最终文本，UI 收到 final 时建议覆盖一次以处理边界差异
    - delta 可能为空字符串（流未产出新可见文本时不发，但调用方应宽松对待）
    - followup 仅 M3 连续答疑模式产生，未启用或 LLM 决策不追问时不出现
    """

    type: StudentStreamEventType = Field(..., description="事件类型")
    delta: str = Field(default="", description="增量文本（仅 type=delta 时有意义）")
    result: DialogReplyResult | None = Field(
        default=None,
        description="最终结构化结果（仅 type=final 时非空）",
    )
    new_question: StudentQuestion | None = Field(
        default=None,
        description="M3 学生主动抛出的新问题（仅 type=followup 时非空）",
    )
