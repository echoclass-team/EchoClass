"""Lesson plan schemas for RAG pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.student import PersonaSummary


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


class LessonUploadData(BaseModel):
    lesson_id: str = Field(..., description="教案唯一标识")
    subject: str = Field(..., description="学科，如'数学'")
    grade: str = Field(..., description="年级，如'三年级'")
    topic: str = Field(..., description="课题名称")
    objectives: list[str] = Field(default_factory=list, description="教学目标")
    key_points: list[str] = Field(default_factory=list, description="教学重点")
    difficult_points: list[str] = Field(default_factory=list, description="教学难点")
    reused: bool = Field(
        default=False,
        description=(
            "本次上传是否命中了该用户已有同内容教案的缓存：True 表示未重新"
            "解析 / 索引，直接复用了已存在的 ``lesson_id`` 与 Chroma 切片。"
        ),
    )


class LessonListItem(BaseModel):
    """教案列表项（用于 GET /api/lessons）。"""

    lesson_id: str
    title: str = ""
    subject: str = ""
    grade: str = ""
    topic: str = ""
    filename: str = ""
    created_at: str = ""
    objectives: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    difficult_points: list[str] = Field(default_factory=list)


class RecommendedPersonasData(BaseModel):
    """教案推荐学生响应数据。"""

    lesson_id: str = Field(..., description="教案唯一标识")
    subject: str = Field(..., description="学科，如'数学'")
    grade: str = Field(..., description="年级，如'三年级'")
    topic: str = Field(..., description="课题名称")
    stage_id: str = Field(..., description="推导出的学段 id")
    stage_name: str = Field(default="", description="学段名称")
    recommended_count: int = Field(..., description="实际推荐学生数量")
    persona_ids: list[str] = Field(default_factory=list, description="推荐学生 id 列表")
    students: list[PersonaSummary] = Field(
        default_factory=list, description="推荐学生概要"
    )
