"""学生人设与课堂上下文相关的 Pydantic 模型。

包含：
- Persona：学生人设（兼容简易 4 字段 和 data/personas/ 完整 18 字段两种模式）
- PersonaSummary：人设概要（API 列表用）
- ClassroomContext：课堂上下文（科目、话题、对话历史）
- load_personas()：从 JSON 文件加载人设列表

学生在 1v1 答疑陪练中的回复模型参见 ``schemas.dialog.DialogReplyResult``。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class TheoryAnchor(BaseModel):
    """Persona ↔ 教育学理论 的轻量锚定（POC 阶段，正式版会迁到 SQLite）。

    通过 ``(theory_id, trait)`` 组合定位到 ``data/edu_theories/<theory_id>.json``
    里的 ``traits[trait]``，从而把该 trait 的 ``operational_rules`` 注入 prompt。
    """

    theory_id: str = Field(
        ..., description="理论卡片 id，对应 data/edu_theories/<id>.json"
    )
    trait: str = Field(
        ..., description="理论的 trait 变体 key，对应卡片里 traits 字典的某个 key"
    )


class Persona(BaseModel):
    """学生人设描述。

    兼容两种构造方式：
    1. 简易模式（3 字段）：name / knowledge_level / behavior_traits
    2. 完整模式（从 data/personas/*.json 加载）。

    Schema 变更历史：
    - v1.3 (2026-05-07) 移除 3 个字段：personality / catchphrases / family_background。
      人设质感由 speech_style + behavior_traits + theory_anchors + summary 联合承载。
    - v1.2 (2026-04-27) 新增 theory_anchors。
    - v1.1 (2026-04-25) 移除 4 个死字段（cognitive_stage / interaction_frequency /
      emotional_tendency / learning_motivation）；认知阶段由 stage.piaget_stage 统一约束。
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

    # --- 语言风格 ---
    speech_style: str = Field(default="", description="说话风格描述")

    # --- 迷思概念 ---
    misconception_tendencies: list[str] = Field(
        default_factory=list, description="容易产生的迷思概念倾向"
    )

    # --- 行为与交互 ---
    attention_span: str = Field(
        default="medium", description="注意力：short/medium/long"
    )
    behavior_traits: str | list[str] = Field(
        ..., description="课堂行为倾向（字符串或列表）"
    )

    # --- 系统辅助 ---
    avatar_seed: str = Field(default="", description="头像种子")
    summary: str = Field(default="", description="一句话概括")

    # --- 教育学理论锚点（POC，向后兼容默认空） ---
    theory_anchors: list[TheoryAnchor] = Field(
        default_factory=list,
        description="该 persona 锚定的教育学理论 trait 列表。空表示不注入理论上下文，等同于旧行为。",
    )

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
    key_points: list[str] = Field(default_factory=list, description="教学重点")
    difficult_points: list[str] = Field(default_factory=list, description="教学难点")
