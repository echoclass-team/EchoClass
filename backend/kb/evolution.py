"""教育学知识库进化引擎（issue #84 Phase 1.C 骨架）。

本期范围（骨架 + 状态机 + 审计）::

    EvolutionEngine
      ├─ record_observation()           运行时观察事件写入
      ├─ submit_misconception_candidate()  LLM 检测的候选迷思入库
      ├─ assign_candidate_for_review()  candidate → reviewing
      ├─ review_candidate()             reviewing → approved / rejected / merged
      ├─ add_anchor()                   持久化新增锚点 + 审计
      └─ remove_anchor()                删除锚点 + 审计

不在本期（留第二期）：

- 自动化 LLM 候选检测器（与第二期评估侧 LLM-as-Judge 一同上）
- confidence 动态更新算法（基于 ``theory_confirmed/violated`` 计数）
- session 钩子接进化引擎（本期 ``record_observation`` 是手动调用）

设计原则：

- 状态机用纯 Python 校验 + DB CHECK 双保险，非法转换抛 ``ValueError``
- 每次状态变更同时写一条 ``Observation`` 做 audit trail（``event_type='evolution'``
  + payload 含 from/to 状态）
- 引擎方法**接受可选 session**（外部已有事务时复用），否则自己起 ``get_session()``
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from kb.database import get_session as _default_get_session
from kb.models import (
    ANCHOR_TARGET_TYPES,
    OBSERVATION_EVENT_TYPES,
    MisconceptionCandidate,
    Observation,
    TheoryAnchor,
    TheoryTrait,
)

logger = logging.getLogger(__name__)


# ============================================================ 状态机定义

# 候选迷思合法状态转换表
# (from, to) ∈ TRANSITIONS 才允许
_CANDIDATE_TRANSITIONS: set[tuple[str, str]] = {
    ("candidate", "reviewing"),
    ("candidate", "approved"),  # 跳过 reviewing 直审（小项目可用）
    ("candidate", "rejected"),
    ("candidate", "merged"),
    ("reviewing", "approved"),
    ("reviewing", "rejected"),
    ("reviewing", "merged"),
    ("reviewing", "candidate"),  # 撤回审核
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================ 引擎


CandidateDecision = Literal["approved", "rejected", "merged"]


class EvolutionEngine:
    """KB 进化引擎（无状态，方法可单独调用）。

    所有写操作要么用调用方传入的 session，要么自己起一个。session 退出时
    上下文管理器负责 commit / rollback。
    """

    def __init__(self, *, session_factory=None) -> None:
        """``session_factory`` 默认走 ``kb.database.get_session``，
        测试时可注入 :memory: 库的工厂。"""
        self._get_session = session_factory or _default_get_session

    @contextmanager
    def _session_or_existing(self, sess: Session | None) -> Iterator[Session]:
        """如果外部已传 session 则直接用，否则起一个新的。"""
        if sess is not None:
            yield sess
        else:
            with self._get_session() as s:
                yield s

    # ---------------------------------------------------- Observation

    def record_observation(
        self,
        *,
        event_type: str,
        session_id: str | None = None,
        dialog_id: str | None = None,
        theory_id: str | None = None,
        trait_key: str | None = None,
        persona_id: str | None = None,
        payload: dict[str, Any] | None = None,
        sess: Session | None = None,
    ) -> int:
        """写入一条观察事件。返回 observation id。

        校验 event_type 在白名单里（与 DB CHECK 双保险）。
        """
        if event_type not in OBSERVATION_EVENT_TYPES:
            raise ValueError(
                f"非法 event_type={event_type!r}，应在 {OBSERVATION_EVENT_TYPES}"
            )
        with self._session_or_existing(sess) as s:
            obs = Observation(
                event_type=event_type,
                session_id=session_id,
                dialog_id=dialog_id,
                theory_id=theory_id,
                trait_key=trait_key,
                persona_id=persona_id,
                payload_json=json.dumps(payload or {}, ensure_ascii=False),
            )
            s.add(obs)
            s.flush()  # 拿 id
            return obs.id

    # ---------------------------------------------------- Misconception Candidate

    def submit_misconception_candidate(
        self,
        *,
        student_text: str,
        suggested: dict[str, Any],
        session_id: str | None = None,
        dialog_id: str | None = None,
        sess: Session | None = None,
    ) -> int:
        """提交一个 LLM 检测到的候选迷思。返回 candidate id。"""
        with self._session_or_existing(sess) as s:
            cand = MisconceptionCandidate(
                student_text=student_text,
                suggested_misconception_json=json.dumps(suggested, ensure_ascii=False),
                session_id=session_id,
                dialog_id=dialog_id,
                status="candidate",
            )
            s.add(cand)
            s.flush()
            # 同时写一条 observation 作为审计
            self.record_observation(
                event_type="misconception_candidate",
                session_id=session_id,
                dialog_id=dialog_id,
                payload={"candidate_id": cand.id},
                sess=s,
            )
            return cand.id

    def assign_candidate_for_review(
        self,
        candidate_id: int,
        *,
        reviewer_id: str,
        sess: Session | None = None,
    ) -> MisconceptionCandidate:
        """``candidate → reviewing``。"""
        with self._session_or_existing(sess) as s:
            cand = self._load_candidate_or_raise(s, candidate_id)
            self._check_transition(cand.status, "reviewing")
            self._record_status_change(
                s,
                cand,
                from_status=cand.status,
                to_status="reviewing",
                reviewer_id=reviewer_id,
                notes="",
            )
            cand.status = "reviewing"
            cand.reviewer_id = reviewer_id
            return cand

    def review_candidate(
        self,
        candidate_id: int,
        *,
        decision: CandidateDecision,
        reviewer_id: str,
        notes: str = "",
        merged_into_id: str | None = None,
        sess: Session | None = None,
    ) -> MisconceptionCandidate:
        """终审：``→ approved | rejected | merged``。

        - decision='merged' 时必须提供 ``merged_into_id``（指向正式 misconception）
        """
        if decision not in ("approved", "rejected", "merged"):
            raise ValueError(f"非法 decision={decision!r}")
        if decision == "merged" and not merged_into_id:
            raise ValueError("decision='merged' 必须提供 merged_into_id")

        with self._session_or_existing(sess) as s:
            cand = self._load_candidate_or_raise(s, candidate_id)
            self._check_transition(cand.status, decision)

            self._record_status_change(
                s,
                cand,
                from_status=cand.status,
                to_status=decision,
                reviewer_id=reviewer_id,
                notes=notes,
                extra={"merged_into_id": merged_into_id} if merged_into_id else None,
            )
            cand.status = decision
            cand.reviewer_id = reviewer_id
            cand.reviewed_at = _utcnow()
            cand.review_notes = notes
            if merged_into_id:
                cand.merged_into_id = merged_into_id
            return cand

    # ---------------------------------------------------- Anchor 增删

    def add_anchor(
        self,
        *,
        theory_id: str,
        trait_key: str,
        target_type: str,
        target_id: str,
        confidence: float = 1.0,
        sess: Session | None = None,
    ) -> TheoryAnchor:
        """新增锚点（已存在则返回原行，不重复创建）+ 审计。"""
        if target_type not in ANCHOR_TARGET_TYPES:
            raise ValueError(
                f"非法 target_type={target_type!r}，应在 {ANCHOR_TARGET_TYPES}"
            )

        with self._session_or_existing(sess) as s:
            # 先校验 trait 存在（FK 之外加 Python 校验给出更友好错误）
            if s.get(TheoryTrait, (theory_id, trait_key)) is None:
                raise ValueError(f"理论 trait 不存在: {theory_id}:{trait_key}")

            stmt = select(TheoryAnchor).where(
                TheoryAnchor.theory_id == theory_id,
                TheoryAnchor.trait_key == trait_key,
                TheoryAnchor.target_type == target_type,
                TheoryAnchor.target_id == target_id,
            )
            existing = s.execute(stmt).scalar_one_or_none()
            if existing is not None:
                return existing

            anchor = TheoryAnchor(
                theory_id=theory_id,
                trait_key=trait_key,
                target_type=target_type,
                target_id=target_id,
                confidence=confidence,
            )
            s.add(anchor)
            s.flush()

            self.record_observation(
                event_type="anchor_added",
                theory_id=theory_id,
                trait_key=trait_key,
                payload={
                    "anchor_id": anchor.id,
                    "target_type": target_type,
                    "target_id": target_id,
                },
                sess=s,
            )
            return anchor

    def remove_anchor(
        self,
        *,
        theory_id: str,
        trait_key: str,
        target_type: str,
        target_id: str,
        sess: Session | None = None,
    ) -> bool:
        """删除锚点 + 审计。返回是否真的删除了一行。"""
        with self._session_or_existing(sess) as s:
            stmt = select(TheoryAnchor).where(
                TheoryAnchor.theory_id == theory_id,
                TheoryAnchor.trait_key == trait_key,
                TheoryAnchor.target_type == target_type,
                TheoryAnchor.target_id == target_id,
            )
            anchor = s.execute(stmt).scalar_one_or_none()
            if anchor is None:
                return False

            anchor_snapshot = {
                "anchor_id": anchor.id,
                "target_type": target_type,
                "target_id": target_id,
            }
            s.delete(anchor)
            s.flush()
            self.record_observation(
                event_type="anchor_removed",
                theory_id=theory_id,
                trait_key=trait_key,
                payload=anchor_snapshot,
                sess=s,
            )
            return True

    # ---------------------------------------------------- 私有

    @staticmethod
    def _load_candidate_or_raise(
        s: Session, candidate_id: int
    ) -> MisconceptionCandidate:
        cand = s.get(MisconceptionCandidate, candidate_id)
        if cand is None:
            raise LookupError(f"候选迷思不存在: id={candidate_id}")
        return cand

    @staticmethod
    def _check_transition(from_status: str, to_status: str) -> None:
        if (from_status, to_status) not in _CANDIDATE_TRANSITIONS:
            raise ValueError(
                f"非法状态转换: {from_status!r} → {to_status!r}。"
                f"允许的转换：{sorted(_CANDIDATE_TRANSITIONS)}"
            )

    def _record_status_change(
        self,
        s: Session,
        cand: MisconceptionCandidate,
        *,
        from_status: str,
        to_status: str,
        reviewer_id: str,
        notes: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        payload = {
            "candidate_id": cand.id,
            "from": from_status,
            "to": to_status,
            "reviewer_id": reviewer_id,
            "notes": notes,
        }
        if extra:
            payload.update(extra)
        self.record_observation(
            event_type="candidate_reviewed",
            session_id=cand.session_id,
            dialog_id=cand.dialog_id,
            payload=payload,
            sess=s,
        )


__all__ = [
    "EvolutionEngine",
    "CandidateDecision",
]
