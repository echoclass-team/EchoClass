"""学科迷思库 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Misconception(BaseModel):
    """data/misconceptions/*.json 中的一条学科迷思。"""

    id: str = Field(..., description="迷思唯一标识")
    subject: str = Field(..., description="学科")
    stage: list[str] = Field(default_factory=list, description="适用学段 id 列表")
    topic: str = Field(..., description="主题")
    name: str = Field(..., description="迷思名称")
    description: str = Field(..., description="迷思描述")
    typical_error: str = Field(..., description="典型错误表现")
    cause: str = Field(..., description="成因")
