"""Lesson upload & retrieval API routes (Issue #19).

POST /api/lessons/upload — 上传教案文件（PDF/MD/TXT），返回 lesson_id + 抽取结果。
GET  /api/lessons/{lesson_id} — 获取教案元数据。
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.response import ok_response
from llm.client import LLMClient
from rag.extractor import extract_lesson_meta
from rag.indexer import index_lesson
from rag.parser import parse_bytes
from schemas.api import ApiResponse
from schemas.lesson import LessonMeta, LessonRecord, LessonUploadData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

_store: dict[str, LessonRecord] = {}


@router.post("/upload", response_model=ApiResponse[LessonUploadData])
async def upload_lesson(file: UploadFile = File(...)) -> ApiResponse[LessonUploadData]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    try:
        text = parse_bytes(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    llm = LLMClient()
    meta = await extract_lesson_meta(llm, text)

    lesson_id = uuid.uuid4().hex[:12]
    chunk_count = index_lesson(lesson_id, text)

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

    return ok_response(
        LessonUploadData(
            lesson_id=lesson_id,
            subject=meta.subject,
            grade=meta.grade,
            topic=meta.topic,
            objectives=meta.objectives,
            key_points=meta.key_points,
            difficult_points=meta.difficult_points,
        )
    )


@router.get("/{lesson_id}", response_model=ApiResponse[LessonRecord])
async def get_lesson(lesson_id: str) -> ApiResponse[LessonRecord]:
    record = _store.get(lesson_id)
    if not record:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return ok_response(record)
