"""Lesson upload & retrieval API routes (Issue #19).

POST /api/lessons/upload — 上传教案文件（PDF/MD/TXT），返回 lesson_id + 抽取结果。
GET  /api/lessons/{lesson_id} — 获取教案元数据。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from api.deps import CurrentUser, get_current_user
from api.response import ok_response
from db.crud import (
    delete_lesson,
    get_lesson_by_hash,
    get_lesson_by_id,
    list_lessons_by_owner,
    save_lesson,
)
from llm.client import LLMClient
from rag.extractor import extract_lesson_meta
from rag.indexer import index_lesson
from rag.parser import parse_bytes
from schemas.api import ApiResponse
from schemas.lesson import (
    LessonListItem,
    LessonMeta,
    LessonRecord,
    LessonUploadData,
    RecommendedPersonasData,
)
from schemas.student import PersonaSummary, load_personas
from schemas.stage import load_stage_profile_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

_store: dict[str, LessonRecord] = {}


def get_lesson_record(lesson_id: str) -> LessonRecord | None:
    """供其他 API 路由（如 ``api/qa_sessions.py``）查询教案。

    优先内存缓存，miss 时查 DB 并回填缓存。
    """
    if lesson_id in _store:
        return _store[lesson_id]
    # DB fallback
    from db.engine import SessionLocal
    db = SessionLocal()
    try:
        row = get_lesson_by_id(db, lesson_id)
        if row is None:
            return None
        meta = LessonMeta(**json.loads(row.meta_json))
        record = LessonRecord(
            lesson_id=row.id,
            filename=row.filename,
            meta=meta,
            text_length=row.text_length,
            chunk_count=row.chunk_count,
        )
        _store[lesson_id] = record
        return record
    finally:
        db.close()


_CHINESE_GRADE_TO_NUMBER = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def infer_stage_id_from_grade(grade: str) -> str | None:
    """根据常见中文/代号年级格式推导学段 id。"""
    normalized = grade.strip().upper().replace(" ", "")
    if not normalized:
        return None

    if "高中" in normalized:
        return "h"

    code_match = re.search(r"\b([PJH])\s*([1-6])\b", normalized)
    if code_match:
        prefix, number_text = code_match.groups()
        number = int(number_text)
        if prefix == "P":
            if number in (1, 2):
                return "p_lower"
            if number in (3, 4):
                return "p_middle"
            if number in (5, 6):
                return "p_upper"
        if prefix == "J":
            if number in (1, 2):
                return "j_lower"
            if number == 3:
                return "j_upper"
        if prefix == "H" and number in (1, 2, 3):
            return "h"

    if "初一" in normalized or "初1" in normalized:
        return "j_lower"
    if "初二" in normalized or "初2" in normalized:
        return "j_lower"
    if "初三" in normalized or "初3" in normalized:
        return "j_upper"
    if "初中" in normalized:
        if "一年级" in normalized or "1年级" in normalized:
            return "j_lower"
        if "二年级" in normalized or "2年级" in normalized:
            return "j_lower"
        if "三年级" in normalized or "3年级" in normalized:
            return "j_upper"
    if "高一" in normalized or "高1" in normalized:
        return "h"
    if "高二" in normalized or "高2" in normalized:
        return "h"
    if "高三" in normalized or "高3" in normalized:
        return "h"

    digit_match = re.search(r"([1-9])年级", normalized)
    if digit_match:
        number = int(digit_match.group(1))
    else:
        chinese_match = re.search(r"([一二三四五六七八九])年级", normalized)
        number = (
            _CHINESE_GRADE_TO_NUMBER[chinese_match.group(1)] if chinese_match else 0
        )

    if number in (1, 2):
        return "p_lower"
    if number in (3, 4):
        return "p_middle"
    if number in (5, 6):
        return "p_upper"
    if number in (7, 8):
        return "j_lower"
    if number == 9:
        return "j_upper"

    return None


def _to_persona_summary(persona) -> PersonaSummary:
    return PersonaSummary(
        id=persona.id,
        name=persona.name,
        gender=persona.gender,
        grade=persona.grade,
        age=persona.age,
        stage_id=persona.stage_id,
        subject_level=persona.effective_level,
        summary=persona.summary,
    )


@router.post("/upload", response_model=ApiResponse[LessonUploadData])
async def upload_lesson(
    file: UploadFile = File(...),
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse[LessonUploadData]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()[:16]

    # dedup：同一用户重复上传完全相同的文件内容 → 直接复用已有 lesson_id
    # 与 Chroma 切片，不再调用 parser / extractor / indexer，避免重复消耗
    # LLM token 与向量库空间（#132）。
    from db.engine import SessionLocal
    db = SessionLocal()
    try:
        existing = get_lesson_by_hash(db, content_hash, _user.id)
    finally:
        db.close()
    if existing is not None:
        try:
            meta = LessonMeta(**json.loads(existing.meta_json))
        except (ValueError, TypeError) as e:
            # 理论上 meta_json 永远是 LessonMeta 的合法 dump；若损坏则降级走重建路径
            logger.warning(
                "stale meta_json for lesson %s, falling back to re-ingest: %s",
                existing.id,
                e,
            )
        else:
            record = LessonRecord(
                lesson_id=existing.id,
                filename=existing.filename,
                meta=meta,
                text_length=existing.text_length,
                chunk_count=existing.chunk_count,
            )
            _store[existing.id] = record
            logger.info(
                "Reused lesson %s for owner %s (hash=%s)",
                existing.id,
                _user.id,
                content_hash,
            )
            return ok_response(
                LessonUploadData(
                    lesson_id=existing.id,
                    subject=meta.subject,
                    grade=meta.grade,
                    topic=meta.topic,
                    objectives=meta.objectives,
                    key_points=meta.key_points,
                    difficult_points=meta.difficult_points,
                    reused=True,
                )
            )

    try:
        text = parse_bytes(content, file.filename)
    except ValueError as e:
        # 不支持的扩展名等业务校验错误
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        # 解析器内部异常（如 PDF 损坏 / pymupdf 报错）— 翻成 422，避免
        # 裸 500 让前端看到不可读错误。issue #101 附带要求。
        logger.exception("parse_bytes failed for %s", file.filename)
        raise HTTPException(status_code=422, detail=f"解析失败：{e}") from e

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

    db = SessionLocal()
    try:
        save_lesson(
            db,
            lesson_id=lesson_id,
            owner_id=_user.id,
            content_hash=content_hash,
            filename=file.filename,
            title=meta.topic,
            meta_json=meta.model_dump_json(),
            text_length=len(text),
            chunk_count=chunk_count,
        )
    finally:
        db.close()

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
            reused=False,
        )
    )


@router.get("", response_model=ApiResponse[list[LessonListItem]])
async def list_lessons(
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse[list[LessonListItem]]:
    """列出当前用户的所有教案。"""
    from db.engine import SessionLocal
    db = SessionLocal()
    try:
        rows = list_lessons_by_owner(db, _user.id)
        items = []
        for r in rows:
            meta = json.loads(r.meta_json) if r.meta_json else {}
            items.append(LessonListItem(
                lesson_id=r.id,
                title=r.title or meta.get("topic", ""),
                subject=meta.get("subject", ""),
                grade=meta.get("grade", ""),
                topic=meta.get("topic", ""),
                filename=r.filename or "",
                created_at=r.created_at.isoformat() if r.created_at else "",
                objectives=meta.get("objectives", []),
                key_points=meta.get("key_points", []),
                difficult_points=meta.get("difficult_points", []),
            ))
        return ok_response(items)
    finally:
        db.close()


@router.get("/{lesson_id}", response_model=ApiResponse[LessonRecord])
async def get_lesson(
    lesson_id: str,
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse[LessonRecord]:
    record = _store.get(lesson_id)
    if not record:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return ok_response(record)


@router.get(
    "/{lesson_id}/recommended-personas",
    response_model=ApiResponse[RecommendedPersonasData],
)
async def recommend_personas_for_lesson(
    lesson_id: str,
    count: int = Query(4, ge=1, le=8, description="推荐学生数量，1-8"),
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse[RecommendedPersonasData]:
    record = _store.get(lesson_id)
    if not record:
        raise HTTPException(status_code=404, detail="Lesson not found")

    grade = record.meta.grade
    stage_id = infer_stage_id_from_grade(grade)
    if not stage_id:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot infer stage_id from lesson grade: {grade}",
        )

    stage = load_stage_profile_by_id(stage_id)
    matched = [p for p in load_personas() if p.stage_id == stage_id][:count]
    students = [_to_persona_summary(p) for p in matched]

    return ok_response(
        RecommendedPersonasData(
            lesson_id=record.lesson_id,
            subject=record.meta.subject,
            grade=grade,
            topic=record.meta.topic,
            stage_id=stage_id,
            stage_name=stage.name if stage else "",
            recommended_count=len(students),
            persona_ids=[student.id for student in students],
            students=students,
        )
    )


@router.delete("/{lesson_id}", response_model=ApiResponse[dict])
async def delete_lesson_endpoint(
    lesson_id: str,
    _user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> ApiResponse[dict]:
    """删除教案（仅限上传者）。同时清除内存缓存。"""
    from db.engine import SessionLocal
    db = SessionLocal()
    try:
        deleted = delete_lesson(db, lesson_id, _user.id)
    finally:
        db.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Lesson not found or not owned by you")
    _store.pop(lesson_id, None)
    logger.info("Deleted lesson %s by user %s", lesson_id, _user.id)
    return ok_response({"lesson_id": lesson_id, "deleted": True})
