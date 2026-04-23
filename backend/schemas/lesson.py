"""Lesson plan schemas for RAG pipeline (Issue #19)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LessonMeta(BaseModel):
    """LLM 抽取的教案结构化元数据。"""

    subject: str = Field(..., description="学科，如'数学'")
    grade: str = Field(..., description="年级，如'三年级'")
    topic: str = Field(..., description="课题名称")
    objectives: list[str] = Field(default_factory=list, description="教学目标")
    key_points: list[str] = Field(default_factory=list, description="教学重点")
    difficult_points: list[str] = Field(default_factory=list, description="教学难点")


class LessonRecord(BaseModel):
    """完整教案记录（元数据 + 索引信息）。"""

    lesson_id: str = Field(..., description="教案唯一标识")
    filename: str = Field(..., description="原始文件名")
    meta: LessonMeta = Field(..., description="LLM 抽取的元数据")
    text_length: int = Field(default=0, description="解析后文本字符数")
    chunk_count: int = Field(default=0, description="向量切片数量")
