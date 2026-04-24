"""学生人设查询 API。

GET /api/personas              — 列出全部人设（支持 stage_id / subject_level 过滤）
GET /api/personas/{name_or_id} — 按姓名或 UUID 查询单个人设详情
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from schemas.student import Persona, load_personas

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("", response_model=list[dict])
async def list_personas(
    stage_id: str | None = Query(None, description="按学段过滤，如 p_lower / j_upper"),
    subject_level: str | None = Query(None, description="按学业水平过滤，如 优秀 / 中等 / 薄弱"),
) -> list[dict]:
    """返回人设概要列表，支持可选的学段和学业水平过滤。"""
    personas = load_personas()
    if stage_id:
        personas = [p for p in personas if p.stage_id == stage_id]
    if subject_level:
        personas = [p for p in personas if p.effective_level == subject_level]
    return [
        {
            "id": p.id,
            "name": p.name,
            "gender": p.gender,
            "grade": p.grade,
            "age": p.age,
            "stage_id": p.stage_id,
            "subject_level": p.effective_level,
            "summary": p.summary,
        }
        for p in personas
    ]


@router.get("/{name_or_id}", response_model=Persona)
async def get_persona(name_or_id: str) -> Persona:
    """按姓名或 UUID 查询单个人设的完整信息。"""
    personas = load_personas()
    for p in personas:
        if p.name == name_or_id or p.id == name_or_id:
            return p
    raise HTTPException(
        status_code=404, detail=f"Persona '{name_or_id}' not found"
    )
