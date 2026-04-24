"""学段认知特征库 Schema (StageProfile)。

基于皮亚杰认知发展阶段论、维果茨基最近发展区、埃里克森心理社会发展理论，
以及教育部《中小学心理健康教育指导纲要》和《义务教育课程方案（2022 年版）》，
将 6-18 岁分为 6 个学段，每个学段描述群体共性特征（与 Persona 个体差异解耦）。
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class StageProfile(BaseModel):
    """学段认知与心理特征描述。

    一个 StageProfile 描述某学段学生的**群体共性**（认知天花板、语言风格、
    社会情感特征、典型迷思范式等）。Persona 描述**个体差异**，通过 stage_id
    关联到某个 StageProfile。
    """

    # --- 基础信息 ---
    id: str = Field(
        ...,
        description="学段唯一标识：p_lower / p_middle / p_upper / j_lower / j_upper / h",
    )
    name: str = Field(..., description="学段名称，如'小学低年级'")
    grade_range: str = Field(..., description="年级范围，如'P1-P2'")
    age_range: str = Field(..., description="年龄范围，如'6-8 岁'")

    # --- 认知发展 ---
    piaget_stage: str = Field(..., description="皮亚杰认知发展阶段")
    cognitive_features: list[str] = Field(
        default_factory=list,
        description="核心认知特征（3-6 条）",
    )
    thinking_style: str = Field(..., description="思维方式概括描述")

    # --- 语言与表达 ---
    language_style: str = Field(..., description="典型语言风格")
    typical_expressions: list[str] = Field(
        default_factory=list,
        description="该学段学生常用的表达/口头禅/句式",
    )

    # --- 注意力与记忆 ---
    attention_features: str = Field(..., description="注意力特征")
    memory_features: str = Field(..., description="记忆特征")

    # --- 社会情感 ---
    erikson_stage: str = Field(..., description="埃里克森心理社会阶段")
    emotional_features: list[str] = Field(
        default_factory=list,
        description="情绪与情感特征",
    )
    self_awareness: str = Field(..., description="自我意识水平")
    peer_relationship: str = Field(..., description="同伴关系特征")

    # --- 学习动机 ---
    motivation_patterns: list[str] = Field(
        default_factory=list,
        description="学习动机模式",
    )

    # --- 课堂行为 ---
    classroom_behaviors: list[str] = Field(
        default_factory=list,
        description="典型课堂行为",
    )
    common_misconception_patterns: list[str] = Field(
        default_factory=list,
        description="该学段常见的迷思概念范式（跨学科通用）",
    )

    # --- 教学启示 ---
    teaching_implications: list[str] = Field(
        default_factory=list,
        description="对师范生的教学启示（供 StudentAgent 反向约束 LLM）",
    )

    # --- 来源 ---
    sources: list[str] = Field(
        default_factory=list,
        description="理论与政策依据",
    )


def load_stage_profiles(
    stage_profiles_dir: str | Path | None = None,
) -> list[StageProfile]:
    """从 data/stage_profiles/ 目录加载所有学段特征 JSON。

    Parameters
    ----------
    stage_profiles_dir : path, optional
        学段目录，默认为项目根下的 data/stage_profiles/

    Returns
    -------
    list[StageProfile]
        加载的学段列表（按 id 排序）。
    """
    if stage_profiles_dir is None:
        stage_profiles_dir = (
            Path(__file__).resolve().parent.parent.parent / "data" / "stage_profiles"
        )
    else:
        stage_profiles_dir = Path(stage_profiles_dir)

    stages: list[StageProfile] = []
    for fp in sorted(stage_profiles_dir.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        stages.append(StageProfile(**data))
    return stages


def load_stage_profile_by_id(
    stage_id: str,
    stage_profiles_dir: str | Path | None = None,
) -> StageProfile | None:
    """按 id 加载单个学段特征。"""
    for stage in load_stage_profiles(stage_profiles_dir):
        if stage.id == stage_id:
            return stage
    return None
