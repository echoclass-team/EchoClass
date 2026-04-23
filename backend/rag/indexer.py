"""Lesson plan chunker + Chroma vector indexer.

将教案文本按 ~500 token（≈1000 中文字符）切片，
存入 Chroma 向量数据库，支持按 lesson_id 检索。
"""
from __future__ import annotations

import logging
import os

import chromadb
from chromadb.api import ClientAPI

logger = logging.getLogger(__name__)

# 中文约 2 字符/token；目标 500 token ≈ 1000 chars
_CHARS_PER_TOKEN = 2
_TARGET_TOKENS = 500
_CHUNK_SIZE = _TARGET_TOKENS * _CHARS_PER_TOKEN
_CHUNK_OVERLAP = 100  # chars

COLLECTION_NAME = "lessons"


def get_chroma_client(persist_dir: str | None = None) -> ClientAPI:
    """获取 Chroma 持久化客户端。"""
    path = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    return chromadb.PersistentClient(path=path)


def chunk_text(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[str]:
    """将文本按固定窗口 + 重叠切片。

    Parameters
    ----------
    text : str
        待切片文本。
    chunk_size : int
        每片字符数，默认 1000。
    overlap : int
        相邻片段重叠字符数，默认 100。

    Returns
    -------
    list[str]
        切片列表。
    """
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start >= len(text):
            break
    return chunks


def index_lesson(
    lesson_id: str,
    text: str,
    *,
    persist_dir: str | None = None,
) -> int:
    """切片并索引教案文本到 Chroma。

    Returns
    -------
    int
        写入的切片数量。
    """
    client = get_chroma_client(persist_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    chunks = chunk_text(text)
    if not chunks:
        return 0

    ids = [f"{lesson_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {"lesson_id": lesson_id, "chunk_index": i} for i in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        documents=chunks,
        metadatas=metadatas,
    )

    logger.info("Indexed %d chunks for lesson %s", len(chunks), lesson_id)
    return len(chunks)


def query_lesson(
    query: str,
    lesson_id: str | None = None,
    n_results: int = 5,
    *,
    persist_dir: str | None = None,
) -> list[str]:
    """从 Chroma 中检索相关切片。

    Parameters
    ----------
    query : str
        查询文本。
    lesson_id : str | None
        限定检索范围的教案 ID。
    n_results : int
        返回的最大切片数。

    Returns
    -------
    list[str]
        匹配的文本切片列表。
    """
    client = get_chroma_client(persist_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    where = {"lesson_id": lesson_id} if lesson_id else None
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
    )

    return results["documents"][0] if results["documents"] else []
