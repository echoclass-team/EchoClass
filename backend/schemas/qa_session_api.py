"""``api/qa_sessions.py`` 的请求 / 响应 Pydantic 模型。

这一层是 REST 包装：内部业务对象 ``services.qa_session.QASession`` /
``schemas.dialog.DialogSession`` 不直接暴露给前端，而是通过这里的轻量
DTO 投影后返回，便于前端做严格 schema 校验。

WS 协议复用 ``schemas.ws_events`` 那套帧；REST 这里只负责"拉起 session"
和"问 session 现状"，二者数据形状刻意保持相似（``WsStudentInfo`` 直接复用），
省去前端两套类型。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.dialog import DialogMessage, DialogStatus, ResolutionSource
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from schemas.ws_events import WsStudentInfo


class CreateQASessionRequest(BaseModel):
    """``POST /api/qa-sessions`` 请求体。"""

    lesson_id: str = Field(
        ..., description="已上传教案的 id（来自 /api/lessons/upload）"
    )
    persona_ids: list[str] = Field(
        ...,
        min_length=1,
        description="参与本次答疑的学生人设 id 列表，至少一个",
    )
    count_per_student: int = Field(
        default=3,
        ge=1,
        le=8,
        description="每个学生生成的问题数量，1-8。默认 3",
    )


class CreateQASessionData(BaseModel):
    """``POST /api/qa-sessions`` 响应数据。

    返回前端继续 setup 所需的全部信息：
    - ``session_id`` / ``ws_url``：用于建立 WebSocket
    - ``lesson`` / ``students`` / ``questions``：与 WS 首帧 ``session_init``
      内容对齐，前端可在跳转 1v1 页面前先渲染骨架
    """

    session_id: str = Field(..., description="新建 session 的唯一 id")
    ws_url: str = Field(
        ..., description="对应的 WebSocket 路径，例 /ws/qa-sessions/{id}"
    )
    lesson: LessonMeta = Field(..., description="教案元数据（与上传时一致）")
    students: list[WsStudentInfo] = Field(..., description="参与本次答疑的学生概要")
    questions: list[StudentQuestion] = Field(
        ..., description="所有学生 spawn 出的初始问题，与 WS 首帧 questions 顺序一致"
    )


class DialogStateSummary(BaseModel):
    """单个 dialog 的轻量摘要 + 完整对话历史。

    ``history`` 用于支持页面级导航（组件卸载 / 浏览器后退 / 新 tab）后
    复原对话进度（issue #102）。前端在 `useQASession` 挂载时调一次
    GET `/api/qa-sessions/{id}` 即可 seed reducer，再正常走 WS 增量。

    形态语义
    --------

    - **M2 闯关模式（v1）**：``id == question.id``，一个学生有多个 dialog，
      ``question_preview`` 是该题正文。
    - **M3 连续答疑模式（v2，issue #111）**：``id == student_id``，一个学生
      只有一个 dialog；``question_preview`` 仍是"学生抛出的第一个问题"，
      后续追问通过 ``history`` 中 ``is_new_question=True`` 的消息体现。
    """

    id: str = Field(
        ...,
        description=(
            "dialog id。M2 = question.id；M3 = student_id（每学生唯一 thread）"
        ),
    )
    student_id: str = Field(..., description="提问学生 id")
    student_name: str = Field(..., description="提问学生姓名")
    status: DialogStatus = Field(..., description="当前状态")
    question_preview: str = Field(
        ...,
        description=(
            "问题正文前 80 字符预览（节省 payload）。"
            "M3 连续答疑模式下 = 学生首问的预览。"
        ),
    )
    turn_count: int = Field(default=0, description="已发生的对话轮数（一来一回算一轮）")
    resolution_source: ResolutionSource | None = Field(
        default=None,
        description="结束方式（仅 status=resolved/abandoned 时填）",
    )
    history: list[DialogMessage] = Field(
        default_factory=list,
        description=(
            "完整对话历史，按时间顺序排列：[teacher, student, teacher, student, ...]。"
            "student 回合的 self_resolved 字段记录该轮 LLM 是否输出 [懂了]。"
            "M3 连续答疑模式下，history 可能跨越多个 question："
            "is_new_question=True 的消息标识学生主动追问的回合，question_id 关联到对应 question。"
            "未发生过对话的 dialog 为空数组。"
        ),
    )


class QASessionStateData(BaseModel):
    """``GET /api/qa-sessions/{id}`` 响应数据。

    用于"刷新陪练页"或"summary 页查询"等被动场景；主动状态推送走 WS。
    """

    session_id: str
    lesson: LessonMeta
    students: list[WsStudentInfo]
    dialogs: list[DialogStateSummary]
    pending: int = Field(..., description="status=pending 数量")
    active: int = Field(..., description="status=active 数量")
    resolved: int = Field(..., description="status=resolved 数量")
    abandoned: int = Field(..., description="status=abandoned 数量")


class QASessionEndData(BaseModel):
    """``POST /api/qa-sessions/{id}/end`` 响应数据。"""

    session_id: str
    summary: dict[str, Any] = Field(
        ..., description="``QASession.summary()`` 直接返回的统计字典"
    )


class QASessionEvaluationData(BaseModel):
    """``GET /api/qa-sessions/{id}/evaluation`` 响应数据。

    与 ``docs/api_contract.md §2.6`` 保持一致：

    - HTTP 200 + ``status="done"``：``evaluation`` 与 ``feedback`` 均非空
    - HTTP 202 + ``status="pending"``：评估仍在跑（或尚未触发），轮询即可
    - HTTP 200 + ``status="failed"``：评估或反馈生成失败但已落定，
      ``error`` 给出简要原因；前端可据此显示 retry / fallback 文案
    """

    status: Literal["done", "pending", "failed"] = Field(
        ..., description="评估状态。前端据此决定渲染 / 轮询 / 报错"
    )
    evaluation: EvaluationReport | None = Field(
        default=None,
        description="评估报告（``status=done`` 时非空）",
    )
    feedback: TeacherFeedback | None = Field(
        default=None,
        description="师范生反馈（``status=done`` 时非空）",
    )
    error: str | None = Field(
        default=None,
        description="``status=failed`` 时给出的简要错误信息",
    )
