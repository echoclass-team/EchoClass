"""Lesson upload & retrieval API routes (Issue #19).

POST /api/lessons/upload — 上传教案文件（PDF/MD/TXT），返回 lesson_id + 抽取结果。
GET  /api/lessons/{lesson_id} — 获取教案元数据。
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from llm.client import LLMClient
from rag.extractor import extract_lesson_meta
from rag.indexer import index_lesson
from rag.parser import parse_bytes
from schemas.lesson import LessonRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

# 内存存储，后续替换为数据库
_store: dict[str, LessonRecord] = {}


@router.post("/upload")
async def upload_lesson(file: UploadFile = File(...)) -> dict:
    """上传教案文件并自动解析、抽取元数据、建立向量索引。

    支持 PDF / Markdown / TXT 格式。

    Returns
    -------
    dict
        包含 lesson_id 及抽取的结构化元数据。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()

    # 1. 解析文件 → 纯文本
    try:
        text = parse_bytes(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. LLM 抽取结构化元数据
    llm = LLMClient()
    meta = await extract_lesson_meta(llm, text)

    # 3. 切片 + 向量索引
    lesson_id = uuid.uuid4().hex[:12]
    chunk_count = index_lesson(lesson_id, text)

    # 4. 存储记录
    record = LessonRecord(
        lesson_id=lesson_id,
        filename=file.filename,
        meta=meta,
        text_length=len(text),
        chunk_count=chunk_count,
    )
    _store[lesson_id] = record

    logger.info(
        "Uploaded lesson %s (%s): %d chars, %d chunks",
        lesson_id,
        file.filename,
        len(text),
        chunk_count,
    )

    return {"lesson_id": lesson_id, **meta.model_dump()}


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str) -> dict:
    """根据 lesson_id 获取教案元数据。"""
    record = _store.get(lesson_id)
    if not record:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return record.model_dump()
