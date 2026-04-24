"""学段认知特征查询 API。

GET /api/stages       — 列出全部 6 档学段概要
GET /api/stages/{id}  — 查询单个学段完整特征
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.response import ok_response
from schemas.api import ApiResponse
from schemas.stage import StageProfile, StageSummary, load_stage_profile_by_id, load_stage_profiles

router = APIRouter(prefix="/api/stages", tags=["stages"])


@router.get("", response_model=ApiResponse[list[StageSummary]])
async def list_stages() -> ApiResponse[list[StageSummary]]:
    stages = load_stage_profiles()
    data = [StageSummary(id=s.id, name=s.name, grade_range=s.grade_range, age_range=s.age_range) for s in stages]
    return ok_response(data)


@router.get("/{stage_id}", response_model=ApiResponse[StageProfile])
async def get_stage(stage_id: str) -> ApiResponse[StageProfile]:
    stage = load_stage_profile_by_id(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage '{stage_id}' not found")
    return ok_response(stage)
