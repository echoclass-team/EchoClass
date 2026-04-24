"""学段特征冒烟测试 — 对比有无 stage 注入时 StudentAgent 回复的差异。

用法:
    cd backend
    uv run python scripts/try_stage_profile.py

测试思路:
- 同一个老师问题"什么是函数？"
- 分别让 3 个不同学段的学生回答（小学低/小学中/高中）
- 观察是否符合学段认知边界：
  · 小学低年级学生：应表示不懂或天真回答
  · 小学中年级学生：可能用生活类比，不用代数术语
  · 高中学生：能给出较严谨的定义
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.stage import load_stage_profile_by_id
from schemas.student import ClassroomContext, load_personas

# 选择 3 个不同学段代表
STAGE_PERSONA_PAIRS = [
    ("p_lower", "张天乐"),   # 小学二年级活泼男孩
    ("p_middle", "陈思远"),  # 小学三年级学霸
    ("h", "许诺"),           # 高二尖子生
]

TEACHER_UTTERANCE = "同学们，你们觉得什么是'函数'？"


async def main() -> None:
    print("=" * 70)
    print("学段特征对比冒烟测试 (with stage vs without stage)")
    print("=" * 70)
    print(f"\n老师问题：{TEACHER_UTTERANCE}\n")

    personas = {p.name: p for p in load_personas()}
    llm = LLMClient()

    for stage_id, persona_name in STAGE_PERSONA_PAIRS:
        persona = personas.get(persona_name)
        stage = load_stage_profile_by_id(stage_id)
        if not persona or not stage:
            print(f"❌ 找不到 persona={persona_name} 或 stage={stage_id}")
            continue

        print("-" * 70)
        print(f"👤 {persona.name}（{stage.name} {persona.grade}, {persona.subject_level}）")
        print("-" * 70)

        # 不带 stage（仅个体 persona）
        agent_no_stage = StudentAgent(
            llm=llm,
            persona=persona,
            context=ClassroomContext(subject="数学", topic="函数概念"),
        )
        reply_no_stage = await agent_no_stage.respond(TEACHER_UTTERANCE)
        print(f"\n[无 stage 约束]")
        print(f"  intent:  {reply_no_stage.intent}")
        print(f"  emotion: {reply_no_stage.emotion}")
        print(f"  content: {reply_no_stage.content}")

        # 带 stage
        agent_with_stage = StudentAgent(
            llm=llm,
            persona=persona,
            context=ClassroomContext(subject="数学", topic="函数概念"),
            stage=stage,
        )
        reply_with_stage = await agent_with_stage.respond(TEACHER_UTTERANCE)
        print(f"\n[有 stage 约束]")
        print(f"  intent:  {reply_with_stage.intent}")
        print(f"  emotion: {reply_with_stage.emotion}")
        print(f"  content: {reply_with_stage.content}")
        print()

    print("=" * 70)
    print("✅ 冒烟测试完成，请人工观察 [有 stage] 的回答是否更贴合年龄段")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
