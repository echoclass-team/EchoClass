"""StudentAgent 相关的 Pydantic 模型。

包含：
- Persona：学生人设（兼容简易 4 字段 和 data/personas/ 完整 18 字段两种模式）
- ClassroomContext：课堂上下文（科目、话题、对话历史）
- StudentReply：StudentAgent 的结构化输出（意图 / 内容 / 情绪）
- Intent：4 种回复意图（answer_question / ask_question / off_topic / passive）
- load_personas()：从 JSON 文件加载人设列表
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["answer_question", "ask_question", "off_topic", "passive"]


class Persona(BaseModel):
    """学生人设描述。

    兼容两种构造方式：
    1. 简易模式（4 字段）：name / personality / knowledge_level / behavior_traits
    2. 完整模式（从 data/personas/*.json 加载）：包含全部 18 字段
    """

    # --- 核心身份 ---
    id: str = Field(default="", description="人设唯一标识符 (UUID v4)")
    name: str = Field(..., description="学生姓名")
    gender: str = Field(default="", description="性别")
    grade: str = Field(default="", description="年级，如 P3 / J1")
    age: int = Field(default=0, description="年龄")
    stage_id: str = Field(
        default="",
        description="关联的学段 id，对应 data/stage_profiles/*.json（如 p_middle / j_lower）",
    )

    # --- 认知与学业 ---
    subject_level: str = Field(default="", description="学科水平：优秀/中等/薄弱")
    personality: str = Field(..., description="性格特征描述")
    cognitive_stage: str = Field(
        default="",
        description="皮亚杰认知阶段：concrete_operational / formal_operational",
    )

    # --- 语言风格 ---
    speech_style: str = Field(default="", description="说话风格描述")
    catchphrases: list[str] = Field(default_factory=list, description="口头禅列表")

    # --- 迷思概念 ---
    misconception_tendencies: list[str] = Field(
        default_factory=list, description="容易产生的迷思概念倾向"
    )

    # --- 行为与交互 ---
    attention_span: str = Field(
        default="medium", description="注意力：short/medium/long"
    )
    interaction_frequency: str = Field(
        default="medium", description="互动频率：low/medium/high"
    )
    behavior_traits: str | list[str] = Field(
        ..., description="课堂行为倾向（字符串或列表）"
    )

    # --- 心理与背景 ---
    emotional_tendency: str = Field(default="", description="情绪倾向描述")
    learning_motivation: str = Field(
        default="", description="学习动机：intrinsic/extrinsic/low"
    )
    family_background: str = Field(default="", description="家庭背景描述")

    # --- 系统辅助 ---
    avatar_seed: str = Field(default="", description="头像种子")
    summary: str = Field(default="", description="一句话概括")

    # --- 兼容旧字段 ---
    knowledge_level: str = Field(
        default="", description="知识水平（兼容旧接口，优先使用 subject_level）"
    )

    @property
    def effective_level(self) -> str:
        """获取有效的知识水平（优先 subject_level）。"""
        return self.subject_level or self.knowledge_level or "中等"

    @property
    def behavior_traits_text(self) -> str:
        """行为特征转为文本。"""
        if isinstance(self.behavior_traits, list):
            return "、".join(self.behavior_traits)
        return self.behavior_traits


class PersonaSummary(BaseModel):
    id: str = Field(..., description="人设唯一标识符")
    name: str = Field(..., description="学生姓名")
    gender: str = Field(..., description="性别")
    grade: str = Field(..., description="年级")
    age: int = Field(..., description="年龄")
    stage_id: str = Field(..., description="关联学段 id")
    subject_level: str = Field(..., description="学科水平")
    summary: str = Field(..., description="一句话概括")

def load_personas(personas_dir: str | Path | None = None) -> list[Persona]:
    """从 data/personas/ 目录加载所有人设 JSON。

    Parameters
    ----------
    personas_dir : path, optional
        人设目录，默认为项目根下的 data/personas/

    Returns
    -------
    list[Persona]
        加载的人设列表（按 name 排序）。
    """
    if personas_dir is None:
        personas_dir = (
            Path(__file__).resolve().parent.parent.parent / "data" / "personas"
        )
    else:
        personas_dir = Path(personas_dir)

    personas: list[Persona] = []
    for fp in sorted(personas_dir.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        personas.append(Persona(**data))
    return personas


class ClassroomContext(BaseModel):
    """当前课堂上下文。"""

    subject: str = Field(..., description="科目，如'数学'")
    topic: str = Field(..., description="当前话题，如'分数的概念'")
    history: list[str] = Field(
        default_factory=list,
        description="之前的课堂对话摘要",
    )


class StudentReply(BaseModel):
    """StudentAgent 的结构化输出。"""

    speaker_id: str = Field(..., description="学生标识")
    intent: Intent = Field(..., description="回复意图")
    content: str = Field(..., description="回复文本")
    emotion: str = Field(..., description="当前情绪，如'困惑'、'自信'、'无聊'")
