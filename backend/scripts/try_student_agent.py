#!/usr/bin/env python3
"""StudentAgent 真实 API 冒烟测试。

用法（在 backend/ 目录下执行）：
    uv run python scripts/try_student_agent.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.student import ClassroomContext, Persona

# ---------- 3 个人设 ----------

PERSONAS = [
    Persona(
        name="小红",
        personality="内向害羞",
        knowledge_level="基础薄弱",
        behavior_traits="沉默寡言，不敢举手",
    ),
    Persona(
        name="小明",
        personality="活泼好动",
        knowledge_level="中等水平",
        behavior_traits="偶尔走神，但会积极回答",
    ),
    Persona(
        name="小华",
        personality="认真严谨",
        knowledge_level="优等生",
        behavior_traits="积极举手，乐于帮助同学",
    ),
]

CONTEXT = ClassroomContext(
    subject="数学",
    topic="分数的概念与运算",
    history=[],
)

UTTERANCE = "同学们，什么是分数？谁能告诉我？"


async def main() -> None:
    llm = LLMClient()
    print(f"✅ LLMClient 初始化成功 (model={llm.model})")
    print(f"📡 base_url={llm.base_url}\n")

    for persona in PERSONAS:
        ctx = CONTEXT.model_copy(deep=True)
        agent = StudentAgent(llm=llm, persona=persona, context=ctx)

        print(f"--- {persona.name}（{persona.knowledge_level}，{persona.personality}）---")
        reply = await agent.respond(UTTERANCE)
        print(f"  intent:  {reply.intent}")
        print(f"  content: {reply.content}")
        print(f"  emotion: {reply.emotion}")
        print()

    print("🎉 全部测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
