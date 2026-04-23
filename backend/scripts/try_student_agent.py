#!/usr/bin/env python3
"""StudentAgent 真实 API 冒烟测试。

自动加载 data/personas/ 下的全部人设 JSON，用真实 API 验证每个学生的回复。

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
from schemas.student import ClassroomContext, load_personas

CONTEXT = ClassroomContext(
    subject="数学",
    topic="分数的概念与运算",
    history=[],
)

UTTERANCE = "同学们，什么是分数？谁能告诉我？"


async def main() -> None:
    personas = load_personas()
    print(f"📂 加载了 {len(personas)} 个人设（来自 data/personas/）\n")

    llm = LLMClient()
    print(f"✅ LLMClient 初始化成功 (model={llm.model})")
    print(f"📡 base_url={llm.base_url}\n")

    for persona in personas:
        ctx = CONTEXT.model_copy(deep=True)
        agent = StudentAgent(llm=llm, persona=persona, context=ctx)

        print(f"{'=' * 60}")
        print(
            f"👤 {persona.name}（{persona.grade} {persona.effective_level}）— {persona.summary}"
        )
        if persona.catchphrases:
            print(f"   💬 口头禅: {persona.catchphrases[0]}")
        if persona.misconception_tendencies:
            print(f"   ⚠️  迷思: {persona.misconception_tendencies[0]}")
        print()

        reply = await agent.respond(UTTERANCE)
        print(f"   intent:  {reply.intent}")
        print(f"   content: {reply.content}")
        print(f"   emotion: {reply.emotion}")
        print()

    print("🎉 全部测试通过！所有人设均正常响应。")


if __name__ == "__main__":
    asyncio.run(main())
