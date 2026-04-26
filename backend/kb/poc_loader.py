"""教育学理论卡片 POC 加载器。

读取 ``data/edu_theories/*.json``，把 persona 的 ``theory_anchors`` 解析为
``ResolvedTheory`` 列表，可直接喂给 ``student_chat.j2`` 等模板的 ``resolved_theories``
变量。

设计取舍：
- POC 阶段就用纯 dict + Pydantic 校验，不接 SQLite，避免阻塞探索
- 加载是 lazy + 进程级缓存（``_load_all_theories`` 只跑一次），开发期重启即可生效
- ``resolve_persona_anchors`` 失败（卡片缺失或 trait 不存在）时**抛出明确错误**，
  不静默 fallback —— 错的锚点不应被忽略，要暴露给开发者
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from schemas.student import Persona, TheoryAnchor


# ============================================================ Pydantic 模型


class TheoryTrait(BaseModel):
    """理论的某个 trait 变体（如 'low_self_efficacy'）。"""

    label: str = Field(..., description="trait 中文标签")
    operational_rules: list[str] = Field(
        ..., description="该 trait 在课堂场景下的可观察行为准则", min_length=1
    )


class TheoryCard(BaseModel):
    """单张教育学理论卡片，对应 ``data/edu_theories/<id>.json``。"""

    id: str = Field(..., description="卡片唯一 id")
    name_zh: str = Field(..., description="中文名称")
    name_en: str = Field(default="", description="英文名称")
    scholar: str = Field(..., description="提出者")
    year: int = Field(default=0, description="提出年份")
    school: str = Field(..., description="所属学派")
    summary: str = Field(..., description="2-3 句话概括")
    traits: dict[str, TheoryTrait] = Field(
        ..., description="trait 变体字典", min_length=1
    )
    applies_to: dict[str, bool] = Field(
        default_factory=dict, description="可锚定到哪些对象类型"
    )
    references: list[str] = Field(..., description="文献引用")


class ResolvedTheory(BaseModel):
    """Persona 的一条 ``TheoryAnchor`` 解析后的运行时模型。

    专为 prompt 模板渲染设计：扁平化 trait_label 与 rules，模板侧无需再做嵌套访问。
    """

    theory_id: str
    name_zh: str
    scholar: str
    school: str
    summary: str
    trait_key: str
    trait_label: str
    rules: list[str]


# ============================================================ 加载逻辑


def _default_theories_dir() -> Path:
    """``data/edu_theories/`` 默认路径（仓库根 / data / edu_theories）。"""
    return Path(__file__).resolve().parent.parent.parent / "data" / "edu_theories"


@lru_cache(maxsize=1)
def _load_all_theories(
    theories_dir_str: Optional[str] = None,
) -> dict[str, TheoryCard]:
    """加载目录下所有理论卡片，返回 ``{id: TheoryCard}``。

    用 ``str`` 作为缓存 key（``Path`` 不 hashable in caching 上下文是 OK 的，
    但这里统一用 str 以便测试可注入不同目录）。
    """
    theories_dir = (
        Path(theories_dir_str) if theories_dir_str else _default_theories_dir()
    )
    if not theories_dir.exists():
        raise FileNotFoundError(f"理论卡片目录不存在: {theories_dir}")

    cards: dict[str, TheoryCard] = {}
    for fp in sorted(theories_dir.glob("*.json")):
        if fp.name.startswith("_"):  # 跳过 _schema.json
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        card = TheoryCard(**data)
        if card.id != fp.stem:
            raise ValueError(
                f"卡片 id ({card.id}) 与文件名 ({fp.stem}) 不一致: {fp}"
            )
        if card.id in cards:
            raise ValueError(f"卡片 id 重复: {card.id}")
        cards[card.id] = card
    return cards


def load_theories(
    theories_dir: Path | str | None = None,
) -> dict[str, TheoryCard]:
    """公共入口：加载所有理论卡片。

    Parameters
    ----------
    theories_dir : 可选
        指定卡片目录（用于测试）。生产路径走默认 ``data/edu_theories/``。
    """
    key = str(theories_dir) if theories_dir is not None else None
    return _load_all_theories(key)


def clear_cache() -> None:
    """清缓存（测试用，或手动改 JSON 后强制重读）。"""
    _load_all_theories.cache_clear()


# ============================================================ 解析锚点


def resolve_anchor(
    anchor: TheoryAnchor,
    *,
    theories: dict[str, TheoryCard] | None = None,
) -> ResolvedTheory:
    """把单条 ``TheoryAnchor`` 解析为运行时 ``ResolvedTheory``。

    Raises
    ------
    KeyError
        卡片或 trait 不存在 —— 不静默 fallback，避免掩盖配置错误
    """
    if theories is None:
        theories = load_theories()
    card = theories.get(anchor.theory_id)
    if card is None:
        raise KeyError(
            f"理论卡片不存在: {anchor.theory_id}（可用: {sorted(theories.keys())}）"
        )
    trait = card.traits.get(anchor.trait)
    if trait is None:
        raise KeyError(
            f"理论 {anchor.theory_id} 没有 trait '{anchor.trait}'"
            f"（可用: {sorted(card.traits.keys())}）"
        )
    return ResolvedTheory(
        theory_id=card.id,
        name_zh=card.name_zh,
        scholar=card.scholar,
        school=card.school,
        summary=card.summary,
        trait_key=anchor.trait,
        trait_label=trait.label,
        rules=list(trait.operational_rules),
    )


def resolve_persona_anchors(
    persona: Persona,
    *,
    theories: dict[str, TheoryCard] | None = None,
) -> list[ResolvedTheory]:
    """把 ``persona.theory_anchors`` 解析为 ``ResolvedTheory`` 列表。

    Persona 没有锚点时返回空列表（等同关闭理论注入）。
    """
    if not persona.theory_anchors:
        return []
    if theories is None:
        theories = load_theories()
    return [resolve_anchor(a, theories=theories) for a in persona.theory_anchors]
