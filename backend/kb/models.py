"""教育学知识库 SQLAlchemy 模型。

5 张表：

1. ``kb_theory``               理论卡片主表（Bandura / Vygotsky / ...）
2. ``kb_theory_trait``         理论 → trait 变体（low/high efficacy 等）一对多
3. ``kb_theory_anchor``        trait ↔ 目标对象（persona/misconception/rubric_dim）多对多
4. ``kb_observation``          运行时观察事件（本期建表 + 接口；第二期实装写入）
5. ``kb_misconception_candidate``  LLM 检测的候选迷思 + 审核状态机

设计原则：

- **同步 ORM**：本期 KB 操作都在 startup / stand-alone 脚本里跑，无需 async
- **JSON 列降表**：list/dict 字段直接存 JSON 字符串，避免过度规范化
- **状态用 String + CHECK**：枚举值不建表，DB CHECK + Python Literal 双保险
- **表名前缀 ``kb_``**：避免与 B 端 M3 将加的 qa_sessions / dialogs 等表冲突
- **本期 confidence/evidence_count 写死**：第二期 evolution 引擎再实装动态更新
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
)


def _utcnow() -> datetime:
    """带 tz 的 UTC 时间戳，供 default 使用。"""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """KB 模块统一的 SQLAlchemy declarative base。

    类名 → snake_case 表名 + ``kb_`` 前缀，避免与 B 端 M3 加的表冲突。
    """

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return f"kb_{name}"


# ============================================================ Theory


class Theory(Base):
    """教育学理论卡片主表（一行 = 一个经典理论）。"""

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), default="")
    scholar: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, default=0)
    school: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    references_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        comment="JSON 序列化 list[str]",
    )
    applies_to_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="JSON: {persona: bool, misconception: bool, rubric: bool}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    traits: Mapped[list["TheoryTrait"]] = relationship(
        back_populates="theory",
        cascade="all, delete-orphan",
        order_by="TheoryTrait.trait_key",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Theory id={self.id!r} name={self.name_zh!r}>"


class TheoryTrait(Base):
    """理论的某个 trait 变体（如 low_self_efficacy）。复合主键。"""

    theory_id: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)
    trait_key: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    operational_rules_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON 序列化 list[str] 行为准则",
    )

    __table_args__ = (
        ForeignKeyConstraint(["theory_id"], ["kb_theory.id"], ondelete="CASCADE"),
    )

    theory: Mapped[Theory] = relationship(back_populates="traits")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TheoryTrait {self.theory_id}:{self.trait_key}>"


# ============================================================ TheoryAnchor


# 锚点目标类型（DB CHECK + Python 校验双保险）
ANCHOR_TARGET_TYPES: tuple[str, ...] = ("persona", "misconception", "rubric_dim")


class TheoryAnchor(Base):
    """trait ↔ 目标对象 多对多关系（多态：target_type + target_id）。"""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trait_key: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="persona name / misconception id / rubric 维度 key",
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["theory_id", "trait_key"],
            ["kb_theory_trait.theory_id", "kb_theory_trait.trait_key"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "theory_id",
            "trait_key",
            "target_type",
            "target_id",
            name="uq_anchor_trait_target",
        ),
        CheckConstraint(
            f"target_type IN {ANCHOR_TARGET_TYPES!r}",
            name="ck_anchor_target_type",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_anchor_confidence_range",
        ),
        Index("ix_anchor_target", "target_type", "target_id"),
        Index("ix_anchor_theory", "theory_id", "trait_key"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TheoryAnchor {self.theory_id}:{self.trait_key} "
            f"→ {self.target_type}:{self.target_id}>"
        )


# ============================================================ Observation


OBSERVATION_EVENT_TYPES: tuple[str, ...] = (
    "theory_confirmed",  # 行为符合 trait
    "theory_violated",  # 行为违反 trait
    "misconception_candidate",  # 检测到候选迷思（详情见候选表）
    "anchor_added",  # 审计：新增锚点
    "anchor_removed",  # 审计：移除锚点
    "candidate_reviewed",  # 审计：候选迷思状态流转
    "evolution",  # 预留通用进化事件
)


class Observation(Base):
    """运行时观察事件（本期建表 + 写入接口；第二期接 session 钩子触发）。"""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dialog_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    theory_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trait_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    persona_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="JSON 自由结构；event_type 决定 schema",
    )

    __table_args__ = (
        CheckConstraint(
            f"event_type IN {OBSERVATION_EVENT_TYPES!r}",
            name="ck_observation_event_type",
        ),
        Index("ix_observation_event", "event_type", "observed_at"),
        Index("ix_observation_theory", "theory_id", "trait_key"),
        Index("ix_observation_persona", "persona_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Observation #{self.id} {self.event_type} @{self.observed_at}>"


# ============================================================ Misconception Candidate


CANDIDATE_STATUSES: tuple[str, ...] = (
    "candidate",  # 初始：LLM 检测到，等审核
    "reviewing",  # 已分配给审核者
    "approved",  # 通过 → 应转为正式 misconception
    "rejected",  # 驳回 → 不入正式库
    "merged",  # 合并到已有 misconception
)


class MisconceptionCandidate(Base):
    """LLM 检测的候选迷思 + 人工审核状态机。

    状态流转（由 ``kb.evolution.EvolutionEngine.review_candidate`` 守护）::

        candidate → reviewing → approved
                              → rejected
                              → merged

    本期实装：建表 + 状态机骨架 + 审计写入。
    本期不实装：LLM 检测器（依赖第二期评估侧 LLM-as-Judge 一同上）。
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dialog_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    student_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="触发该候选的学生原话",
    )
    suggested_misconception_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON: LLM 生成的迷思建议结构（subject/stage/key_point/...）",
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    merged_into_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="status='merged' 时指向正式 misconception id",
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN {CANDIDATE_STATUSES!r}",
            name="ck_candidate_status",
        ),
        Index("ix_candidate_status", "status", "detected_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MisconceptionCandidate #{self.id} status={self.status!r}>"


# ============================================================ 导出清单


__all__ = [
    "Base",
    "Theory",
    "TheoryTrait",
    "TheoryAnchor",
    "Observation",
    "MisconceptionCandidate",
    "ANCHOR_TARGET_TYPES",
    "OBSERVATION_EVENT_TYPES",
    "CANDIDATE_STATUSES",
]
