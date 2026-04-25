"""QA 答疑陪练 WebSocket 协议事件模型 (#71)。

定义 1v1 师范生答疑陪练 WebSocket 端点 (`/ws/qa-sessions/{session_id}`)
所有客户端 / 服务端消息的 Pydantic 结构。

设计原则：

- **JSON Lines** 一帧一条 JSON，每条消息有 ``type`` 字段做 discriminated union
- **服务端 → 客户端** 每条消息带单调递增的 ``seq``（连接生命周期内唯一），
  客户端可据此检测乱序 / 丢帧
- **客户端 → 服务端** 每条消息带可选 ``timestamp``（ISO-8601）便于排错
- 嵌入对象（``LessonMeta`` / ``StudentQuestion``）直接复用业务 schema，避免
  双份维护；客户端自行根据需要取用字段

事件序列示例（一次完整 1v1 对话）::

    S→C: session_init                          # 连上后立刻推
    C→S: select_dialog(dialog_id=q1)
    S→C: dialog_active(dialog_id=q1)
    C→S: teacher_message(dialog_id=q1, text="…")
    S→C: reply_chunk(dialog_id=q1, delta="哦", chunk_seq=0)
    S→C: reply_chunk(dialog_id=q1, delta="，原来…", chunk_seq=1)
    ...
    S→C: reply_end(dialog_id=q1, full_content="…", self_resolved=False)
    C→S: teacher_message(dialog_id=q1, text="…")  # 多轮
    ...
    C→S: resolve(dialog_id=q1, source="teacher_marked")
    S→C: dialog_resolved(dialog_id=q1, source="teacher_marked")
    ...
    C→S: <connection close>
    S→C: summary(data={...})                    # 关闭前推，可选

约束：

- **单 session 单连接**：第二次连同一 session 时，旧连接收到
  ``error(code="replaced")`` 并被关闭
- 同一 ``dialog_id`` 的 ``reply_chunk`` 序列**保证有序**，且 ``chunk_seq``
  从 0 单调递增；后端不会把不同 dialog 的 chunk 交错（单 session 串行处理）
- 流式 ``reply_chunk.delta`` 已经在 agent 侧做过 hold-back 缓冲，
  **绝不会**包含末尾 ``[懂了]`` 标记字符。前端可无脑拼接 delta，
  ``reply_end`` 到达时再用 ``full_content`` 校正一次显示文本

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from schemas.dialog import ResolutionSource
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion


# ---------------------------------------------------------------- 共享小模型


class WsStudentInfo(BaseModel):
    """``session_init`` 中传给前端的学生概要（轻量版 Persona）。

    仅含前端 UI 必须的展示字段，避免把整份 18 字段 Persona 推给前端。
    """

    id: str = Field(..., description="学生 id（== Persona.id 或 name 兜底）")
    name: str = Field(..., description="学生姓名")
    stage_id: str = Field(default="", description="所属学段 id")
    subject_level: str = Field(default="", description="学科水平：优秀/中等/薄弱")
    avatar_seed: str = Field(default="", description="头像种子（前端用以生成 avatar）")
    summary: str = Field(default="", description="一句话概括人设")


WsErrorCode = Literal[
    "dialog_not_found",  # dialog_id 不存在
    "dialog_already_ended",  # dialog 已 resolved / abandoned
    "session_not_found",  # session_id 不存在
    "invalid_message",  # 客户端帧无法解析 / 字段缺失
    "replaced",  # 同 session 新连接挤掉本连接
    "llm_failed",  # LLM 上游错误
    "internal_error",  # 其他后端异常
]
"""WS error.code 枚举。"""


# ------------------------------------------------------------ 客户端 → 服务端


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _ClientBase(BaseModel):
    """客户端帧公共基类。"""

    timestamp: datetime = Field(
        default_factory=_now, description="客户端发送时间（可选，便于排错）"
    )


class WsSelectDialog(_ClientBase):
    """师范生从队列里挑选一个学生提问进入 1v1 对话。

    服务端响应 ``dialog_active``。如果 dialog 已经 active，幂等返回。
    """

    type: Literal["select_dialog"] = "select_dialog"
    dialog_id: str = Field(..., description="目标对话 id（== StudentQuestion.id）")


class WsTeacherMessage(_ClientBase):
    """师范生在某个 active dialog 内发言。

    服务端响应 0..N 个 ``reply_chunk`` + 一个 ``reply_end``。
    若 dialog 处于 ``pending``，服务端会自动 ``start_dialog`` 后再处理。
    """

    type: Literal["teacher_message"] = "teacher_message"
    dialog_id: str = Field(..., description="目标对话 id")
    text: str = Field(..., min_length=1, description="师范生本轮发言（非空）")


class WsResolve(_ClientBase):
    """师范生标记 dialog 已解答。

    服务端响应 ``dialog_resolved``。``source`` 区分是师范生主动点确认
    （``teacher_marked``），还是承认学生 ``[懂了]`` 自我宣称（``self_resolve``）。
    """

    type: Literal["resolve"] = "resolve"
    dialog_id: str = Field(..., description="目标对话 id")
    source: ResolutionSource = Field(
        default="teacher_marked", description="结束方式来源"
    )


class WsAbandon(_ClientBase):
    """师范生放弃 dialog。

    服务端响应 ``dialog_abandoned``。dialog 转为 ``abandoned`` 状态后
    不再可继续；切换到下一个学生用 ``select_dialog``。
    """

    type: Literal["abandon"] = "abandon"
    dialog_id: str = Field(..., description="目标对话 id")


WsClientEvent = Annotated[
    Union[WsSelectDialog, WsTeacherMessage, WsResolve, WsAbandon],
    Field(discriminator="type"),
]
"""所有客户端 → 服务端事件的 discriminated union。

解码用法::

    from pydantic import TypeAdapter
    adapter = TypeAdapter(WsClientEvent)
    event = adapter.validate_json(raw_frame)
"""


# ------------------------------------------------------------ 服务端 → 客户端


class _ServerBase(BaseModel):
    """服务端帧公共基类，包含单调递增的 ``seq``。"""

    seq: int = Field(..., ge=0, description="服务端单调递增帧序号（连接内唯一）")
    timestamp: datetime = Field(
        default_factory=_now, description="服务端生成时间"
    )


class WsSessionInit(_ServerBase):
    """连接建立后服务端立刻推送的初始化帧。

    包含本次答疑会话的全部上下文：教案、学生列表、初始问题队列。
    前端用这一帧渲染左侧学生列表 + 右侧待办问题红点。
    """

    type: Literal["session_init"] = "session_init"
    session_id: str = Field(..., description="QA session 唯一标识")
    lesson: LessonMeta = Field(..., description="教案元数据（直接复用 LessonMeta）")
    students: list[WsStudentInfo] = Field(
        default_factory=list, description="本场参与的学生列表"
    )
    questions: list[StudentQuestion] = Field(
        default_factory=list,
        description=(
            "学生们已经主动构思好的问题队列（即所有 dialog 的入口问题）；"
            "顺序与 ``QASession.next_pending`` 弹出顺序一致"
        ),
    )


class WsDialogActive(_ServerBase):
    """``select_dialog`` 的响应：dialog 已切换为 active。"""

    type: Literal["dialog_active"] = "dialog_active"
    dialog_id: str = Field(..., description="进入 active 的对话 id")


class WsReplyChunk(_ServerBase):
    """流式学生回复的一个增量分片。

    delta 不会含末尾 ``[懂了]`` 标记（agent 侧已用 hold-back 缓冲过滤）。
    前端按到达顺序拼接即可；最终以 ``reply_end.full_content`` 为权威文本。
    """

    type: Literal["reply_chunk"] = "reply_chunk"
    dialog_id: str = Field(..., description="本 chunk 所属 dialog id")
    delta: str = Field(..., description="增量文本片段")
    chunk_seq: int = Field(
        ..., ge=0, description="同 dialog 内 chunk 序号，从 0 递增"
    )


class WsReplyEnd(_ServerBase):
    """学生本轮回复流式输出结束。

    ``self_resolved=True`` 表示学生在末尾说了 ``[懂了]``：
    前端建议弹一个确认 toast「XXX 表示懂了，标记为已解答吗？」让师范生确认，
    确认后客户端发 ``resolve(source="self_resolve")``。
    """

    type: Literal["reply_end"] = "reply_end"
    dialog_id: str = Field(..., description="本回复所属 dialog id")
    full_content: str = Field(..., description="完整回复文本（已剥离标记）")
    self_resolved: bool = Field(
        default=False, description="LLM 是否在末尾标记了 [懂了]"
    )


class WsDialogResolved(_ServerBase):
    """``resolve`` 的响应：dialog 转为 resolved。"""

    type: Literal["dialog_resolved"] = "dialog_resolved"
    dialog_id: str = Field(..., description="已解决的 dialog id")
    source: ResolutionSource = Field(..., description="结束方式来源")


class WsDialogAbandoned(_ServerBase):
    """``abandon`` 的响应：dialog 转为 abandoned。"""

    type: Literal["dialog_abandoned"] = "dialog_abandoned"
    dialog_id: str = Field(..., description="已放弃的 dialog id")


class WsSummary(_ServerBase):
    """会话总结。

    通常在客户端断连前 / 显式请求时推送。``data`` 直接是
    ``QASession.summary()`` 的返回结构（字段见 ``services/qa_session.py``）。
    """

    type: Literal["summary"] = "summary"
    data: dict[str, Any] = Field(
        ..., description="QASession.summary() 返回的 dict"
    )


class WsError(_ServerBase):
    """服务端错误帧。

    出现 ``code="replaced"`` 时连接将被服务端关闭（被新连接挤掉）。
    其他 code 不一定关闭连接，前端按需做容错。
    """

    type: Literal["error"] = "error"
    code: WsErrorCode = Field(..., description="错误码（受控枚举）")
    message: str = Field(..., description="人类可读的错误描述")
    dialog_id: str | None = Field(
        default=None, description="关联的 dialog id（若有）"
    )


WsServerEvent = Annotated[
    Union[
        WsSessionInit,
        WsDialogActive,
        WsReplyChunk,
        WsReplyEnd,
        WsDialogResolved,
        WsDialogAbandoned,
        WsSummary,
        WsError,
    ],
    Field(discriminator="type"),
]
"""所有服务端 → 客户端事件的 discriminated union。"""


__all__ = [
    "WsClientEvent",
    "WsServerEvent",
    "WsSelectDialog",
    "WsTeacherMessage",
    "WsResolve",
    "WsAbandon",
    "WsSessionInit",
    "WsDialogActive",
    "WsReplyChunk",
    "WsReplyEnd",
    "WsDialogResolved",
    "WsDialogAbandoned",
    "WsSummary",
    "WsError",
    "WsErrorCode",
    "WsStudentInfo",
]
