"""DialogSession 模型 — 1v1 答疑陪练的对话会话。

会话有明确的状态流转::

    pending → active → resolved | abandoned

``resolution_source`` 记录"是怎么解决的"，便于事后区分"师范生真破除"和
"学生自我宣称懂了"。

形态演进
--------

**闯关模式（v1，已上线）**
    每个 ``DialogSession`` 1:1 对应一个 ``StudentQuestion``：一个学生可能持有
    N 个 dialog（每题一个），师范生从队列里挑题进入 1v1。
    ``messages`` 内全部消息都属于 ``dialog.question`` 这一道题。

**连续答疑模式（v2，当前实现）**
    每个 ``DialogSession`` 1:1 对应一个**学生**（``student_id``）：一个学生只
    有一个 dialog。``spawn`` 时一次性预生成 N 道题（当前 N=3），按序放入
    ``asked_questions``，并以对齐的 ``question_progress`` 记录每题进度。

    推进规则（确定性，不再调用 LLM 决策）：

    - 首问（``asked_questions[0]``）直接作为 dialog 的入口抛出
    - 当前题收到学生 ``[懂了]`` 标记 → 单题标 ``resolved``，指针推进，自动
      把下一题作为 ``DialogMessage(is_new_question=True)`` 抛出（复用
      ``followup`` stream event 通道）
    - 当前题累计 turn 数超过上限 M（当前 M=8）→ 单题标 ``abandoned``
      （``resolution_source='turn_limit'``），指针推进同上
    - 指针越过最后一题 → 整个 ``DialogSession`` 标 ``resolved``

    ``dialog.question`` 保留为首问（==``asked_questions[0]``），向后兼容。

两种形态在字段层完全兼容：
- v1 的 ``DialogMessage`` 永远 ``is_new_question=False`` / ``question_id=None``
- v2 引入新字段 + 新 WS 帧 ``student_new_question``（见 ``ws_events``）
- v2 给 ``DialogSession`` 加了 ``asked_questions`` / ``question_progress`` /
  ``current_question_idx`` 字段；M2 模式下 ``asked_questions`` 仅含首问、
  ``question_progress`` 为空列表、``current_question_idx=0``，向后兼容
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
    "turn_limit",  # 单题累计 turn 数超过上限被自动作废（dialog 整体仍可继续到下一题）
]


class DialogMessage(BaseModel):
    """单条对话消息。

    连续答疑模式下，一个 dialog 内可能跨越多个 ``StudentQuestion``：
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
            "连续答疑模式下，仅 role='student' 时可能为 True：本条消息是学生"
            "主动抛出的新问题（不是对老师上一句的回应）。前端据此渲染'新问题'气泡。"
            "由 ``QASession`` 从 ``asked_questions`` 队列确定性弹出（不再走 "
            "LLM 决策）。闯关模式下永远 False。"
        ),
    )
    question_id: str | None = Field(
        default=None,
        description=(
            "连续答疑模式下，本条消息所属 question 的 id；用于评估时按问题分段。"
            "闯关模式下永远 None（dialog 与 question 一一对应，无需冗余记录）。"
        ),
    )


QuestionStatus = Literal["pending", "active", "resolved", "abandoned"]
"""连续答疑模式下单题的状态：

- ``pending``：题目已预生成，尚未被抛出（在 ``current_question_idx`` 之后）
- ``active``：题目正在被讨论（即 ``current_question_idx`` 指向的那一题）
- ``resolved``：学生已宣称懂了（``[懂了]`` 标记）
- ``abandoned``：已放弃（通常是 ``resolution_source='turn_limit'`` 触发）
"""


class QuestionProgress(BaseModel):
    """连续答疑模式下单道预生成题目的进度追踪。

    与 ``DialogSession.asked_questions`` 按下标对齐；记录单题的运行状态、
    已用轮数、以及该题在 ``DialogSession.messages`` 中的切片范围，供 evaluator
    按题分段引用证据，供编排层判断是否推进到下一题。
    """

    question_id: str = Field(
        ..., description="对应 ``asked_questions[i].id``，便于反向索引"
    )
    status: QuestionStatus = Field(default="pending", description="单题当前状态")
    turns_used: int = Field(
        default=0,
        ge=0,
        description=(
            "本题已累计的师生 turn 数（老师一句 + 学生一句算 1 轮）。"
            "超过上限 M（当前 M=8）时单题自动 ``abandoned``。"
        ),
    )
    message_start_idx: int = Field(
        ...,
        ge=0,
        description="该题在 ``DialogSession.messages`` 中的起始下标（含）",
    )
    message_end_idx: int | None = Field(
        default=None,
        description=(
            "该题在 ``DialogSession.messages`` 中的结束下标（开区间，不含）；"
            "题目结束（resolved/abandoned）时设置"
        ),
    )
    resolution_source: ResolutionSource | None = Field(
        default=None,
        description="单题结束方式；``status='resolved'/'abandoned'`` 时必填",
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
            "连续答疑模式下，``spawn`` 时一次性预生成的全部 N 道题（当前 N=3）。"
            "首问 == ``asked_questions[0]`` == ``question``；后续题按序排列。"
            "运行期长度不变、不追加。供 ``QASession`` 按 ``current_question_idx`` 推进。"
            "闯关模式下仅含首问一项。"
        ),
    )
    question_progress: list[QuestionProgress] = Field(
        default_factory=list,
        description=(
            "连续答疑模式下，与 ``asked_questions`` 按下标对齐的进度列表；每项"
            "记录单题状态、已用轮数、对应的 ``messages`` 切片范围，供 evaluator 按题"
            "分段引用证据。闯关模式下可为空列表。"
        ),
    )
    current_question_idx: int = Field(
        default=0,
        ge=0,
        description=(
            "连续答疑模式下，当前正在讨论的题目在 ``asked_questions`` 中的下标。"
            "指针越过最后一题（``== len(asked_questions)``）表示所有题已结束，整"
            "个 dialog 应被 resolve。闯关模式下永远 0。"
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
- ``followup``：本轮回复后学生主动抛出的新问题。``new_question``
  非空。由 ``QASession.stream_teacher_message`` 在 ``final`` 之后可选追加：
  当本轮学生 ``self_resolved=True`` 或当前题 turn 数达上限时，从
  ``asked_questions`` 队列确定性弹出下一题（不再调用 LLM 决策）。队列空时
  不发出。仅出现一次。
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
    - followup 仅 连续答疑模式产生；当前题未结束或已是最后一题时不出现
    """

    type: StudentStreamEventType = Field(..., description="事件类型")
    delta: str = Field(default="", description="增量文本（仅 type=delta 时有意义）")
    result: DialogReplyResult | None = Field(
        default=None,
        description="最终结构化结果（仅 type=final 时非空）",
    )
    new_question: StudentQuestion | None = Field(
        default=None,
        description="学生主动抛出的新问题（仅 type=followup 时非空）",
    )
    source: str | None = Field(
        default=None,
        description="推进原因（仅 type=followup）：'turn_limit' / 'self_resolve' 等",
    )
