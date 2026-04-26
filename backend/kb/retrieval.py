"""理论卡片向量检索（Chroma 存储）。

设计取舍:

- **粒度 = trait**（不是整张卡片）。每个 trait 的 operational_rules 表达了具体行为，
  把它作为独立 doc 检索，比整卡更容易命中"我想要焦虑学生的描述"这类 query
- **doc id**: ``{theory_id}::{trait_key}``，与 SQL 主键一一对应
- **doc 内容**: trait label + operational_rules + 卡片 summary 拼接
  （summary 给 trait 提供上下文，让纯检索查询不必先知道理论名也能召回）
- **metadata**: theory_id / trait_key / school / scholar / name_zh，
  支持按学派 / 提出者过滤
- **持久化目录**: 与 ``rag/indexer.py`` 共用 ``./chroma_data``（默认）/
  ``CHROMA_PERSIST_DIR``；collection 名 ``edu_theories`` 与 lessons 隔离

⚠️ **已知限制**: 当前用 Chroma 默认 embedding（``all-MiniLM-L6-v2``，英文优化），
中文 query 召回质量较差。第二期评估侧上线前应切换到
``paraphrase-multilingual-MiniLM-L12-v2`` 或 OpenAI ``text-embedding-3-*``。
本期仅保证 collection 存活与基础功能（按 metadata 过滤可用）。

API:

- ``index_all_theories()``: 从 DB 全量重建索引（先清空 collection 再写）
- ``search_theories(query, ...)``: 检索 + 实体水合（合并 SQL 元数据 + Chroma 距离）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import chromadb
from chromadb.api import ClientAPI

from kb.database import get_session
from kb.models import Theory, TheoryTrait

logger = logging.getLogger(__name__)


COLLECTION_NAME = "edu_theories"


def get_chroma_client(persist_dir: str | None = None) -> ClientAPI:
    """获取 Chroma 持久化客户端。与 ``rag/indexer`` 默认一致。"""
    path = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    return chromadb.PersistentClient(path=path)


# ============================================================ 文档构造


def _build_doc_text(card_summary: str, trait_label: str, rules: list[str]) -> str:
    """把 trait 拼成可被嵌入的文本块。"""
    rules_text = "\n".join(f"- {r}" for r in rules)
    return f"【{trait_label}】\n{card_summary}\n\n行为准则:\n{rules_text}"


def _build_metadata(card: Theory, trait: TheoryTrait) -> dict[str, str | int]:
    """Chroma metadata（必须是 str/int/float/bool）。"""
    return {
        "theory_id": card.id,
        "trait_key": trait.trait_key,
        "name_zh": card.name_zh,
        "scholar": card.scholar,
        "school": card.school,
        "year": int(card.year or 0),
        "label": trait.label,
    }


# ============================================================ 索引构建


def index_all_theories(*, persist_dir: str | None = None) -> int:
    """从 SQLite 读取全部理论 + traits，全量重建 Chroma 索引。

    实现策略：先 ``delete_collection`` 再 ``get_or_create``，
    避免增量 upsert 后残留旧 doc。

    Returns
    -------
    int
        写入的 doc 数量。
    """
    client = get_chroma_client(persist_dir)
    # 全量重建：先删后建
    try:
        client.delete_collection(COLLECTION_NAME)
    except (ValueError, Exception) as exc:  # noqa: BLE001
        # collection 不存在时 chroma 会抛 ValueError，可忽略
        logger.debug("delete_collection(%s) skipped: %r", COLLECTION_NAME, exc)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []

    with get_session() as sess:
        cards = sess.query(Theory).all()
        for card in cards:
            for trait in card.traits:
                rules = json.loads(trait.operational_rules_json)
                ids.append(f"{card.id}::{trait.trait_key}")
                docs.append(_build_doc_text(card.summary, trait.label, rules))
                metas.append(_build_metadata(card, trait))

    if not ids:
        logger.warning("KB DB 没有理论卡片，索引未写入任何 doc")
        return 0

    collection.add(ids=ids, documents=docs, metadatas=metas)
    logger.info("Indexed %d theory traits to Chroma", len(ids))
    return len(ids)


# ============================================================ 检索


def search_theories(
    query: str,
    *,
    n_results: int = 5,
    school: str | None = None,
    persist_dir: str | None = None,
) -> list[dict[str, Any]]:
    """混合检索：Chroma 向量召回 + metadata 过滤。

    返回结果按距离升序，每条含 ``theory_id`` / ``trait_key`` /
    ``name_zh`` / ``scholar`` / ``school`` / ``label`` / ``distance`` /
    ``document``。

    Parameters
    ----------
    query : str
        中文 query，如 "焦虑且不敢回答的学生" / "概念冲突如何破除"
    n_results : int
        返回的最大命中数
    school : str, optional
        按学派过滤（精确匹配 metadata.school）
    """
    client = get_chroma_client(persist_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    where = {"school": school} if school else None

    res = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
    )

    out: list[dict[str, Any]] = []
    if not res.get("ids") or not res["ids"][0]:
        return out

    ids = res["ids"][0]
    distances = (res.get("distances") or [[None] * len(ids)])[0]
    documents = (res.get("documents") or [[""] * len(ids)])[0]
    metadatas = (res.get("metadatas") or [[{}] * len(ids)])[0]

    for i, doc_id in enumerate(ids):
        meta = metadatas[i] or {}
        out.append(
            {
                "id": doc_id,
                "theory_id": meta.get("theory_id", ""),
                "trait_key": meta.get("trait_key", ""),
                "name_zh": meta.get("name_zh", ""),
                "scholar": meta.get("scholar", ""),
                "school": meta.get("school", ""),
                "label": meta.get("label", ""),
                "distance": distances[i],
                "document": documents[i],
            }
        )
    return out


__all__ = [
    "COLLECTION_NAME",
    "index_all_theories",
    "search_theories",
    "get_chroma_client",
]
