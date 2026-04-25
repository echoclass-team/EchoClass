"""QASession — 1v1 答疑陪练的轻量编排服务。

设计目标（详见 ``docs/PIVOT.md``）：
- 取代旧的 ``ClassroomGraph`` LangGraph 状态机
- 不是回合制，每个 ``DialogSession`` 是独立的多轮 1v1 对话
- 用普通异步类即可，无需引入图框架

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
from typing import Iterable

from agents.student import StudentAgent
from schemas.dialog import (
    DialogMessage,
    DialogReplyResult,
    DialogSession,
    ResolutionSource,
)
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion

logger = logging.getLogger(__name__)


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

    def __init__(self, *, lesson_meta: LessonMeta, session_id: str | None = None) -> None:
        self.id = session_id or str(uuid.uuid4())
        self.lesson_meta = lesson_meta
        self.dialogs: dict[str, DialogSession] = {}
        # student_id → StudentAgent（spawn 时写入；用于在 send_teacher_message 时查回）
        self._agents: dict[str, StudentAgent] = {}
        # 队列保留 spawn 时的问题顺序，供 next_pending 弹出
        self._pending_order: list[str] = []
        self._created_at = datetime.now(timezone.utc)

    # =================================================================== I/O

    async def spawn(
        self,
        student_agents: Iterable[StudentAgent],
        *,
        questions_per_student: int = 3,
    ) -> list[StudentQuestion]:
        """让每个学生 agent 基于 ``self.lesson_meta`` 生成问题，并入队。

        生成是并行的（``asyncio.gather``），任一学生失败不影响其他。返回**按学生
        提交顺序拼接**的问题列表（学生间穿插由 next_pending 的轮询策略处理）。
        """
        agents = list(student_agents)
        if not agents:
            return []

        results = await asyncio.gather(
            *(self._generate_safe(a, questions_per_student) for a in agents),
            return_exceptions=False,
        )

        all_questions: list[StudentQuestion] = []
        # 轮询交叉：先取每个学生的第 1 题、再第 2 题……让前几个被推送的问题来自不同学生
        max_len = max((len(qs) for qs in results), default=0)
        for round_idx in range(max_len):
            for agent, qs in zip(agents, results):
                if round_idx >= len(qs):
                    continue
                question = qs[round_idx]
                self._agents[question.speaker_id] = agent
                dialog = DialogSession(
                    id=question.id,
                    student_id=question.speaker_id,
                    question=question,
                    status="pending",
                )
                self.dialogs[dialog.id] = dialog
                self._pending_order.append(dialog.id)
                all_questions.append(question)

        logger.info(
            "QASession[%s] spawned %d questions from %d students",
            self.id,
            len(all_questions),
            len(agents),
        )
        return all_questions

    async def _generate_safe(
        self, agent: StudentAgent, count: int
    ) -> list[StudentQuestion]:
        try:
            return await agent.generate_questions(self.lesson_meta, count=count)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "QASession[%s] student %s generate_questions failed: %s",
                self.id,
                agent.persona.name,
                exc,
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
        """把 ``pending`` 对话切为 ``active``。重复调用对已 active 的会话是幂等的。"""
        dialog = self.get_dialog(dialog_id)
        if dialog.status == "active":
            return dialog
        if dialog.status in {"resolved", "abandoned"}:
            raise QASessionError(
                f"dialog {dialog_id} already ended (status={dialog.status})"
            )
        dialog.status = "active"
        dialog.started_at = datetime.now(timezone.utc)
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
            raise QASessionError(
                f"no student agent registered for {dialog.student_id}"
            )

        now = datetime.now(timezone.utc)
        dialog.messages.append(DialogMessage(role="teacher", content=text, timestamp=now))

        result = await agent.respond_in_dialog(
            question=dialog.question,
            teacher_utterance=text,
            dialog_history=dialog.messages[:-1],  # 不含本轮 teacher 消息
        )
        dialog.messages.append(
            DialogMessage(
                role="student",
                content=result.content,
                timestamp=datetime.now(timezone.utc),
            )
        )
        return result

    def mark_resolved(
        self,
        dialog_id: str,
        *,
        source: ResolutionSource = "teacher_marked",
    ) -> DialogSession:
        """把对话标记为 resolved。重复对已 resolved 对话调用是幂等的。"""
        dialog = self.get_dialog(dialog_id)
        if dialog.status == "resolved":
            return dialog
        if dialog.status == "abandoned":
            raise QASessionError(f"dialog {dialog_id} already abandoned")
        dialog.status = "resolved"
        dialog.ended_at = datetime.now(timezone.utc)
        dialog.resolution_source = source
        if dialog_id in self._pending_order:
            self._pending_order.remove(dialog_id)
        logger.info("QASession[%s] resolved dialog %s via %s", self.id, dialog_id, source)
        return dialog

    def abandon_dialog(self, dialog_id: str) -> DialogSession:
        """师范生主动放弃当前对话（切到下一个学生或退出）。"""
        dialog = self.get_dialog(dialog_id)
        if dialog.status in {"resolved", "abandoned"}:
            return dialog
        dialog.status = "abandoned"
        dialog.ended_at = datetime.now(timezone.utc)
        dialog.resolution_source = "abandoned"
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
            d.question.linked_key_point
            for d in resolved
            if d.question.linked_key_point
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
