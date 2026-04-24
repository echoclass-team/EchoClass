"""学段认知特征查询 API。

GET /api/stages       — 列出全部 6 档学段概要
GET /api/stages/{id}  — 查询单个学段完整特征
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas.stage import StageProfile, load_stage_profile_by_id, load_stage_profiles

router = APIRouter(prefix="/api/stages", tags=["stages"])


@router.get("", response_model=list[dict])
async def list_stages() -> list[dict]:
    """返回所有学段的概要信息（id / name / grade_range / age_range）。"""
    stages = load_stage_profiles()
    return [
        {
            "id": s.id,
            "name": s.name,
            "grade_range": s.grade_range,
            "age_range": s.age_range,
        }
        for s in stages
    ]


@router.get("/{stage_id}", response_model=StageProfile)
async def get_stage(stage_id: str) -> StageProfile:
    """返回指定学段的完整认知特征。"""
    stage = load_stage_profile_by_id(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage '{stage_id}' not found")
    return stage
