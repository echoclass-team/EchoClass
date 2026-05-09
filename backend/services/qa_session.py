"""QASession — 1v1 答疑陪练的轻量编排服务。

设计目标：
- 每个 ``DialogSession`` 是独立的多轮 1v1 对话
- 用普通异步类即可承载，无需引入复杂的图框架
- 学生 Agent 主动提问，师范生从问题队列里挑选并 1v1 解答

核心数据流::

    QASession.spawn(lesson_meta, student_agents)        # 1. 让每个学生生成问题，建会话队列
        ↓
    session.next_pending() → DialogSession(status=pending)  # 2. 师范生选下一个问题
        ↓
    session.start_dialog(dialog_id)                     # 3. 标记 active
        ↓
    session.send_teacher_message(dialog_id, text)       # 4. 一来一回多轮
        → DialogReplyResult                                #    返回学生回复 + self_resolved 信号
        ↓
    session.mark_resolved(dialog_id, source=...)        # 5. 师范生 / 学生宣称结束
        ↓
    session.summary()                                   # 6. 退出时全场统计

并发约束：本类**不是线程安全**的，期望由 WebSocket endpoint 串行调用。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Iterable

from agents.student import StudentAgent
from schemas.dialog import (
    DialogMessage,
    DialogReplyResult,
    DialogSession,
    QuestionProgress,
    ResolutionSource,
    StudentStreamEvent,
)
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion

logger = logging.getLogger(__name__)

PRESET_QUESTIONS_PER_STUDENT = 3
"""M3 预生成问题数：每个学生 spawn 时一次性生成的题数。

重要：改动此值要同步更新 ``schemas/dialog.py`` 和 ``docs/api_contract.md`` 中的
N=3 文案。过大（≥5）会显著拉高 spawn 阶段 LLM 输出 tokens，且学生处境难以
支撑 5+ 个互独立的真实问题。
"""

MAX_TURNS_PER_QUESTION = 8
"""M3 单题最大轮数（老师一句 + 学生一句算1 轮）。超过即单题自动 ``abandoned``
（``resolution_source='turn_limit'``）并推进下一题，避免关卡在单题上。
"""


class QASessionError(Exception):
    """QASession 内部业务错误，用于区分非法状态转换 vs LLM 输出问题。"""


class QASession:
    """一个 1v1 答疑陪练 session 的全部状态与编排能力。

    Attributes
    ----------
    id : str
        会话唯一标识。
    lesson_meta : LessonMeta
        本次答疑的教案元数据（题材、重点、难点）。
    dialogs : dict[str, DialogSession]
        所有学生提出的问题对应的对话会话，key 为 dialog_id（== question.id）。
    """

    def __init__(
        self, *, lesson_meta: LessonMeta, session_id: str | None = None
    ) -> None:
        self.id = session_id or str(uuid.uuid4())
        self.lesson_meta = lesson_meta
        self.dialogs: dict[str, DialogSession] = {}
        # student_id → StudentAgent（spawn 时写入；用于在 send_teacher_message 时查回）
        self._agents: dict[str, StudentAgent] = {}
        # 队列保留 spawn 时的问题顺序，供 next_pending 弹出
        self._pending_order: list[str] = []
        self._created_at = datetime.now(timezone.utc)

    # ============================================================= 只读访问器

    def iter_students(self) -> Iterable[tuple[str, StudentAgent]]:
        """按 spawn 注册顺序遍历 ``(student_id, StudentAgent)``。

        给 REST / WS 投影层用，避免下游模块直接访问 ``self._agents`` 私有
        字段。消费者只应读 ``agent.persona``、``agent.persona.name`` 等公开
        属性来构造 DTO（如 ``WsStudentInfo``），不应保留 agent 引用做长期
        持久化。

        顺序与 ``spawn`` 入参一致（dict 维持插入顺序）。
        """
        return self._agents.items()

    # =================================================================== I/O

    async def spawn(
        self,
        student_agents: Iterable[StudentAgent],
        *,
        questions_per_student: int = PRESET_QUESTIONS_PER_STUDENT,
    ) -> list[StudentQuestion]:
        """为每个学生 spawn 一个 thread dialog（M3）。

        每个学生调 ``generate_questions(count=questions_per_student)`` 一次性预生成 N
        道独立问题（缺省 N=``PRESET_QUESTIONS_PER_STUDENT``=3），在本 session 里创建
        **一个** ``DialogSession``（``id == student_id``），全部 N 题按序放入
        ``asked_questions``，对齐 ``question_progress`` 记录每题进度。

        首问即 ``asked_questions[0]``，直接作为 dialog 入口抛出给师范生；后续题
        在单题 resolved（学生 ``[懂了]``）或 ``turn_limit`` 超限时由
        ``send/stream_teacher_message`` 确定性弹出为 ``DialogMessage(is_new_question=True)``。

        生成并行（``asyncio.gather``），任一学生失败不影响其他。返回按学生提交
        顺序的首问列表（**仅首问**，用于对外的问题列表 DTO；后续题可从
        ``dialog.asked_questions`` 取到）。

        Parameters
        ----------
        questions_per_student : int
            每个学生预生成的题目数量。默认 3；传 1 则退化为 M2/早期 M3 行为（
            仅首问，后续题队列为空）。不允许 0 或负数。
        """
        if questions_per_student < 1:
            raise QASessionError(
                f"questions_per_student must be >= 1, got {questions_per_student}"
            )
        agents = list(student_agents)
        if not agents:
            return []

        # 各学生并行生成（预生成 N 题走同一次 ask prompt + self-check + 多样性筛选）。
        results: list[list[StudentQuestion]] = await asyncio.gather(
            *(self._generate_safe(a, count=questions_per_student) for a in agents),
            return_exceptions=False,
        )

        first_questions: list[StudentQuestion] = []
        for agent, qs in zip(agents, results):
            if not qs:
                logger.warning(
                    "QASession[%s] student %s skipped: generate_questions returned empty",
                    self.id,
                    agent.persona.name,
                )
                continue
            student_id = qs[0].speaker_id
            # 首问 id 强绑 student_id，保证 dialog.id == student_id == first_question.id。
            # 后续题保留 LLM 给的 uuid，避免重复。
            normalized: list[StudentQuestion] = [
                qs[0].model_copy(update={"id": student_id, "speaker_id": student_id})
            ]
            for q in qs[1:]:
                normalized.append(q.model_copy(update={"speaker_id": student_id}))
            self._agents[student_id] = agent
            dialog = DialogSession(
                id=student_id,
                student_id=student_id,
                question=normalized[0],
                status="pending",
                asked_questions=normalized,
                question_progress=[
                    QuestionProgress(
                        question_id=q.id,
                        status="pending",
                        turns_used=0,
                        # 所有题预初始化为 0；在 start_dialog / 推进时改写成真实下标
                        message_start_idx=0,
                    )
                    for q in normalized
                ],
                current_question_idx=0,
            )
            self.dialogs[dialog.id] = dialog
            self._pending_order.append(dialog.id)
            first_questions.append(normalized[0])

        logger.info(
            "QASession[%s] spawned %d student threads (N=%d per student)",
            self.id,
            len(first_questions),
            questions_per_student,
            extra={
                "event": "session_spawn",
                "session_id": self.id,
                "student_count": len(first_questions),
                "questions_per_student": questions_per_student,
            },
        )
        return first_questions

    async def _generate_safe(
        self, agent: StudentAgent, *, count: int
    ) -> list[StudentQuestion]:
        try:
            return await agent.generate_questions(self.lesson_meta, count=count)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "QASession[%s] student %s generate_questions failed: %s",
                self.id,
                agent.persona.name,
                exc,
                extra={
                    "event": "generate_questions_failed",
                    "session_id": self.id,
                    "student": agent.persona.name,
                },
            )
            return []

    # =============================================================== queries

    def next_pending(self) -> DialogSession | None:
        """返回下一个 status=pending 的对话；若无则 None。

        FIFO 顺序——先生成的先推送。一旦 ``start_dialog`` 被调用就不再出现在此队列。
        """
        while self._pending_order:
            dialog_id = self._pending_order[0]
            dialog = self.dialogs.get(dialog_id)
            if dialog is None or dialog.status != "pending":
                self._pending_order.pop(0)
                continue
            return dialog
        return None

    def pending_count(self) -> int:
        """剩余未开启对话的问题数。"""
        return sum(1 for d in self.dialogs.values() if d.status == "pending")

    def get_dialog(self, dialog_id: str) -> DialogSession:
        if dialog_id not in self.dialogs:
            raise QASessionError(f"dialog {dialog_id} not found")
        return self.dialogs[dialog_id]

    # ============================================================ transitions

    def start_dialog(self, dialog_id: str) -> DialogSession:
        """把 ``pending`` 对话切为 ``active``。重复调用对已 active 的会话是幂等的。

        M3：同时把 ``question_progress[current_question_idx]`` 标为 ``active``，并绑定
        ``message_start_idx = 0``（首问的所有 message 累加从头开始）。
        """
        dialog = self.get_dialog(dialog_id)
        if dialog.status == "active":
            return dialog
        if dialog.status in {"resolved", "abandoned"}:
            raise QASessionError(
                f"dialog {dialog_id} already ended (status={dialog.status})"
            )
        dialog.status = "active"
        dialog.started_at = datetime.now(timezone.utc)
        # 激活当前题的 progress（如果有 question_progress）
        if dialog.question_progress:
            progress = dialog.question_progress[dialog.current_question_idx]
            progress.status = "active"
            progress.message_start_idx = len(dialog.messages)
        # 从 pending 队列移除
        if dialog_id in self._pending_order:
            self._pending_order.remove(dialog_id)
        logger.debug("QASession[%s] start dialog %s", self.id, dialog_id)
        return dialog

    async def send_teacher_message(
        self, dialog_id: str, text: str
    ) -> DialogReplyResult:
        """老师向某个 active 对话发言，返回学生回复（非流式 MVP 版）。

        - 若 dialog 处于 ``pending``，自动 ``start_dialog``
        - 把老师消息和学生回复都追加到 ``dialog.messages``
        - 学生回复中的 ``[懂了]`` 标记被剥离并以 ``self_resolved`` 标志返回，
          **是否真正结束会话由调用方决定**（通常 = 师范生确认）
        """
        if not text.strip():
            raise QASessionError("teacher message must be non-empty")
        dialog = self.get_dialog(dialog_id)
        if dialog.status == "pending":
            self.start_dialog(dialog_id)
        if dialog.status != "active":
            raise QASessionError(
                f"dialog {dialog_id} not active (status={dialog.status})"
            )

        agent = self._agents.get(dialog.student_id)
        if agent is None:
            raise QASessionError(f"no student agent registered for {dialog.student_id}")

        now = datetime.now(timezone.utc)
        dialog.messages.append(
            DialogMessage(role="teacher", content=text, timestamp=now)
        )

        current_question = self._current_question(dialog)
        result = await agent.respond_in_dialog(
            question=current_question,
            teacher_utterance=text,
            dialog_history=dialog.messages[:-1],  # 不含本轮 teacher 消息
        )
        dialog.messages.append(
            DialogMessage(
                role="student",
                content=result.content,
                timestamp=datetime.now(timezone.utc),
                self_resolved=result.self_resolved,
            )
        )
        self._after_student_reply(dialog, result)
        return result

    async def stream_teacher_message(
        self, dialog_id: str, text: str
    ) -> AsyncIterator[StudentStreamEvent]:
        """``send_teacher_message`` 的流式版本：转发 ``StudentAgent.stream_in_dialog``
        的事件，并在流结束时把完整学生回复落入 dialog 历史。

        与 ``send_teacher_message`` 的语义差异：

        - 调用方拿到一个 async generator，按 ``StudentStreamEvent`` 顺序消费：
          0..N 个 ``delta`` + 1 个 ``final``
        - ``final.result.content`` 是权威完整文本（已剥离 ``[懂了]`` 标记）
        - delta 不含 ``[懂了]``（agent 侧 hold-back 缓冲已过滤）
        - 落库时机：仅在最后一个 ``final`` 事件 yield 之前把 student message 追加到
          dialog.messages，**保证若中途异常不会留下半截消息**

        Yields
        ------
        StudentStreamEvent
        """
        if not text.strip():
            raise QASessionError("teacher message must be non-empty")
        dialog = self.get_dialog(dialog_id)
        if dialog.status == "pending":
            self.start_dialog(dialog_id)
        if dialog.status != "active":
            raise QASessionError(
                f"dialog {dialog_id} not active (status={dialog.status})"
            )

        agent = self._agents.get(dialog.student_id)
        if agent is None:
            raise QASessionError(f"no student agent registered for {dialog.student_id}")

        now = datetime.now(timezone.utc)
        dialog.messages.append(
            DialogMessage(role="teacher", content=text, timestamp=now)
        )

        logger.info(
            "QASession[%s] teacher_message on %s",
            self.id,
            dialog_id,
            extra={
                "event": "teacher_message",
                "session_id": self.id,
                "dialog_id": dialog_id,
                "text_len": len(text),
            },
        )

        current_question = self._current_question(dialog)
        history_snapshot = dialog.messages[:-1]  # 不含本轮 teacher 消息

        final_event: StudentStreamEvent | None = None
        async for evt in agent.stream_in_dialog(
            question=current_question,
            teacher_utterance=text,
            dialog_history=history_snapshot,
        ):
            if evt.type == "final":
                final_event = evt
                # 在 yield final 之前把学生回复落库
                if evt.result is not None:
                    dialog.messages.append(
                        DialogMessage(
                            role="student",
                            content=evt.result.content,
                            timestamp=datetime.now(timezone.utc),
                            self_resolved=evt.result.self_resolved,
                        )
                    )
            yield evt

        if final_event is None:  # pragma: no cover - 防御性
            raise QASessionError(
                f"stream_in_dialog finished without final event for {dialog_id}"
            )
        if final_event.result is not None:
            next_q, advance_source = self._after_student_reply(dialog, final_event.result)
            if next_q is not None:
                yield StudentStreamEvent(type="followup", new_question=next_q, source=advance_source)

    @staticmethod
    def _current_question(dialog: DialogSession) -> StudentQuestion:
        """返回当前正在讨论的题目。

        M3：``asked_questions[current_question_idx]``（确定性指针）。
        M2 / 单问退化：空列表时回调到 ``dialog.question``。
        """
        if not dialog.asked_questions:
            return dialog.question
        idx = min(dialog.current_question_idx, len(dialog.asked_questions) - 1)
        return dialog.asked_questions[idx]

    def _after_student_reply(
        self, dialog: DialogSession, result: DialogReplyResult
    ) -> tuple[StudentQuestion | None, str | None]:
        """学生回复落库后调用，判定是否推进子题。

        规则：

        - ``progress.turns_used += 1``（本轮老师+学生算 1 轮）
        - 若 ``result.self_resolved=True`` → 标单题 ``resolved (self_resolve)`` 并推进
        - 若 ``turns_used >= MAX_TURNS_PER_QUESTION`` → 标单题 ``abandoned (turn_limit)`` 并推进
        - 否则本题继续

        Returns
        -------
        tuple[StudentQuestion | None, str | None]
            (推进后抛出的新题, 推进原因)；若不推进则 ``(None, None)``。
        """
        if not dialog.question_progress:
            return None, None  # M2 退化：没有进度追踪，不推进
        idx = dialog.current_question_idx
        if idx >= len(dialog.question_progress):
            return None, None
        progress = dialog.question_progress[idx]
        progress.turns_used += 1

        if result.self_resolved:
            return self._advance_after_question_end(dialog, source="self_resolve"), "self_resolve"
        if progress.turns_used >= MAX_TURNS_PER_QUESTION:
            return self._advance_after_question_end(dialog, source="turn_limit"), "turn_limit"
        return None, None

    def _advance_after_question_end(
        self,
        dialog: DialogSession,
        *,
        source: ResolutionSource,
    ) -> StudentQuestion | None:
        """关闭当前子题并推进指针；可能抛下一题或结束整 dialog。

        该函数为 ``_after_student_reply``（学生自称懂了 / 超轮限）与
        ``mark_resolved``（老师手动点解答）共用的推进内核。

        Source 映射 ``progress.status``：

        - ``self_resolve`` / ``teacher_marked`` / ``auto_evaluator`` → ``resolved``
        - ``abandoned`` / ``turn_limit`` → ``abandoned``

        Returns
        -------
        StudentQuestion | None
            抛出的下一题；若已是最后一题则 ``None`` 并把 ``dialog`` 整体标 ``resolved``。
        """
        idx = dialog.current_question_idx
        if idx >= len(dialog.question_progress):  # pragma: no cover - 防御性
            return None
        progress = dialog.question_progress[idx]
        if progress.status in {"resolved", "abandoned"}:
            return None  # 幂等：本题已结束
        progress.status = (
            "resolved"
            if source in {"self_resolve", "teacher_marked", "auto_evaluator"}
            else "abandoned"
        )
        progress.resolution_source = source
        progress.message_end_idx = len(dialog.messages)

        next_idx = idx + 1
        dialog.current_question_idx = next_idx

        if next_idx >= len(dialog.asked_questions):
            # 所有题结束，整个 dialog 标 resolved
            dialog.status = "resolved"
            dialog.ended_at = datetime.now(timezone.utc)
            dialog.resolution_source = source
            if dialog.id in self._pending_order:
                self._pending_order.remove(dialog.id)
            logger.info(
                "QASession[%s] dialog %s auto-resolved (last source=%s)",
                self.id,
                dialog.id,
                source,
                extra={
                    "event": "dialog_auto_resolved",
                    "session_id": self.id,
                    "dialog_id": dialog.id,
                    "source": source,
                },
            )
            return None

        # 抛下一题：激活 progress 并 append is_new_question message
        next_q = dialog.asked_questions[next_idx]
        next_progress = dialog.question_progress[next_idx]
        next_progress.status = "active"
        next_progress.message_start_idx = len(dialog.messages)
        dialog.messages.append(
            DialogMessage(
                role="student",
                content=next_q.content,
                timestamp=datetime.now(timezone.utc),
                is_new_question=True,
                question_id=next_q.id,
            )
        )
        logger.info(
            "QASession[%s] dialog %s advance q[%d]/%d prev_src=%s",
            self.id,
            dialog.id,
            next_idx,
            len(dialog.asked_questions),
            source,
            extra={
                "event": "question_advance",
                "session_id": self.id,
                "dialog_id": dialog.id,
                "next_idx": next_idx,
                "prev_source": source,
            },
        )
        return next_q

    def mark_resolved(
        self,
        dialog_id: str,
        *,
        source: ResolutionSource = "teacher_marked",
    ) -> DialogSession:
        """将**当前子题**标记为 resolved 并推进到下一题；若已是最后一题则整个
        dialog 标 ``resolved``。

        M3 语义变化：从旧版"结束整段辅导"改为"结束当前子题并推进"。
        要中途放弃整个学生的辅导，请用 ``abandon_dialog``。

        重复对已结束 dialog 调用是幂等的。
        """
        dialog = self.get_dialog(dialog_id)
        if dialog.status == "resolved":
            return dialog
        if dialog.status == "abandoned":
            raise QASessionError(f"dialog {dialog_id} already abandoned")

        if not dialog.question_progress:
            # M2 退化：无进度追踪，直接结束整个 dialog（保持旧语义）
            dialog.status = "resolved"
            dialog.ended_at = datetime.now(timezone.utc)
            dialog.resolution_source = source
            if dialog_id in self._pending_order:
                self._pending_order.remove(dialog_id)
            logger.info(
                "QASession[%s] resolved dialog %s via %s (M2 fallback)",
                self.id,
                dialog_id,
                source,
                extra={
                    "event": "dialog_resolved",
                    "session_id": self.id,
                    "dialog_id": dialog_id,
                    "source": source,
                },
            )
            return dialog

        self._advance_after_question_end(dialog, source=source)
        return dialog

    def abandon_dialog(self, dialog_id: str) -> DialogSession:
        """师范生主动放弃当前对话（切到下一个学生或退出）。

        M3：整个 dialog 标 ``abandoned``；同时将当前 active 的子题标 ``abandoned``
        并记录 ``message_end_idx``，未开启的 ``pending`` 子题保持原样。
        """
        dialog = self.get_dialog(dialog_id)
        if dialog.status in {"resolved", "abandoned"}:
            return dialog
        dialog.status = "abandoned"
        dialog.ended_at = datetime.now(timezone.utc)
        dialog.resolution_source = "abandoned"
        # 关闭当前 active 子题（如果有）
        if dialog.question_progress:
            idx = dialog.current_question_idx
            if idx < len(dialog.question_progress):
                progress = dialog.question_progress[idx]
                if progress.status == "active":
                    progress.status = "abandoned"
                    progress.resolution_source = "abandoned"
                    progress.message_end_idx = len(dialog.messages)
        if dialog_id in self._pending_order:
            self._pending_order.remove(dialog_id)
        return dialog

    # ============================================================== summary

    def summary(self) -> dict[str, object]:
        """退出时一份会话总结，可直接序列化给前端。"""
        resolved = [d for d in self.dialogs.values() if d.status == "resolved"]
        abandoned = [d for d in self.dialogs.values() if d.status == "abandoned"]
        pending = [d for d in self.dialogs.values() if d.status == "pending"]
        active = [d for d in self.dialogs.values() if d.status == "active"]

        # 按重点维度的覆盖率（去重）
        covered_points = {
            d.question.linked_key_point for d in resolved if d.question.linked_key_point
        }
        # 破除的迷思
        broken_misconceptions = {
            d.question.linked_misconception_id
            for d in resolved
            if d.question.linked_misconception_id
        }

        return {
            "session_id": self.id,
            "lesson_topic": self.lesson_meta.topic,
            "total_questions": len(self.dialogs),
            "resolved": len(resolved),
            "abandoned": len(abandoned),
            "pending": len(pending),
            "active": len(active),
            "covered_key_points": sorted(covered_points),
            "broken_misconception_ids": sorted(broken_misconceptions),
            "resolution_sources": _count_sources(resolved + abandoned),
        }


def _count_sources(dialogs: list[DialogSession]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in dialogs:
        if d.resolution_source is None:
            continue
        counts[d.resolution_source] = counts.get(d.resolution_source, 0) + 1
    return counts
