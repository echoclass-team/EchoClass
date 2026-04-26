"""教育学理论卡片加载器（POC + L3 第一期）。

把 persona 的 ``theory_anchors`` 解析为 ``ResolvedTheory`` 列表，
可直接喂给 ``student_chat.j2`` 等模板的 ``resolved_theories`` 变量。

加载来源（按优先级）:

1. **SQLite KB**（``ECHOCLASS_KB_SOURCE=db`` 或默认值，且库存在 + 有数据时）
2. **JSON 文件**（``data/edu_theories/*.json``，永远作为 fallback）

切换方式：
- 默认（不设环境变量）：尝试 DB，失败则 JSON fallback
- ``ECHOCLASS_KB_SOURCE=json``：强制 JSON 路径（POC 行为，测试常用）
- ``ECHOCLASS_KB_SOURCE=db``：强制 DB 路径，DB 异常会抛错而不是 fallback

设计取舍：

- 加载是 lazy + 进程级缓存（``_load_*_cached`` 只跑一次），开发期重启即可生效
- ``resolve_persona_anchors`` 失败（卡片缺失或 trait 不存在）时**抛出明确错误**，
  不静默 fallback —— 错的锚点不应被忽略，要暴露给开发者
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.student import Persona, TheoryAnchor

logger = logging.getLogger(__name__)


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
def _load_all_theories_from_json(
    theories_dir_str: Optional[str] = None,
) -> dict[str, TheoryCard]:
    """从 JSON 目录加载理论卡片，返回 ``{id: TheoryCard}``。

    用 ``str`` 作为缓存 key（统一用 str 以便测试可注入不同目录）。
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
            raise ValueError(f"卡片 id ({card.id}) 与文件名 ({fp.stem}) 不一致: {fp}")
        if card.id in cards:
            raise ValueError(f"卡片 id 重复: {card.id}")
        cards[card.id] = card
    return cards


@lru_cache(maxsize=1)
def _load_all_theories_from_db() -> dict[str, TheoryCard]:
    """从 SQLite KB 加载理论卡片，返回 ``{id: TheoryCard}``。

    依赖 ``kb.database`` 与 ``kb.models``。库里没数据时返回空 dict（不报错），
    由上层决定是否 fallback 到 JSON。
    """
    # 局部 import 避免循环依赖（database 也在 kb 包内）
    from kb.database import get_session
    from kb.models import Theory as DBTheory

    cards: dict[str, TheoryCard] = {}
    with get_session() as sess:
        for row in sess.query(DBTheory).all():
            traits: dict[str, TheoryTrait] = {}
            for t in row.traits:
                traits[t.trait_key] = TheoryTrait(
                    label=t.label,
                    operational_rules=json.loads(t.operational_rules_json),
                )
            cards[row.id] = TheoryCard(
                id=row.id,
                name_zh=row.name_zh,
                name_en=row.name_en or "",
                scholar=row.scholar,
                year=row.year or 0,
                school=row.school,
                summary=row.summary,
                traits=traits,
                applies_to=json.loads(row.applies_to_json or "{}"),
                references=json.loads(row.references_json or "[]"),
            )
    return cards


KbSource = Literal["auto", "db", "json"]


def _resolve_source() -> KbSource:
    """从环境变量决定加载源。"""
    val = os.environ.get("ECHOCLASS_KB_SOURCE", "auto").strip().lower()
    if val in ("db", "json", "auto"):
        return val  # type: ignore[return-value]
    logger.warning("未知 ECHOCLASS_KB_SOURCE=%r，回退 'auto'", val)
    return "auto"


def load_theories(
    theories_dir: Path | str | None = None,
    *,
    source: KbSource | None = None,
) -> dict[str, TheoryCard]:
    """公共入口：加载所有理论卡片。

    Parameters
    ----------
    theories_dir : 可选
        指定 JSON 卡片目录（仅 JSON 路径有效）。
    source : ``'auto'`` | ``'db'`` | ``'json'``
        覆盖 ``ECHOCLASS_KB_SOURCE`` 环境变量。
        - ``auto``（默认）: 先试 DB；DB 异常或为空时 fallback JSON
        - ``db``: 强制 DB，异常会抛出
        - ``json``: 强制 JSON
    """
    src = source or _resolve_source()
    json_key = str(theories_dir) if theories_dir is not None else None

    if src == "json":
        return _load_all_theories_from_json(json_key)

    if src == "db":
        return _load_all_theories_from_db()

    # ---- auto: DB 优先，fallback JSON
    try:
        cards = _load_all_theories_from_db()
        if cards:
            return cards
        logger.info("KB DB 无数据，fallback 到 JSON 加载")
    except Exception as exc:  # noqa: BLE001
        logger.info("KB DB 加载失败，fallback 到 JSON: %r", exc)
    return _load_all_theories_from_json(json_key)


def clear_cache() -> None:
    """清缓存（测试用，或手动改 JSON / DB 后强制重读）。"""
    _load_all_theories_from_json.cache_clear()
    _load_all_theories_from_db.cache_clear()


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
