#!/usr/bin/env python3
"""DirectorAgent 真实 API 冒烟测试。

用法（在 backend/ 目录下执行）：
    uv run python scripts/try_director.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.director import DirectorAgent
from llm.client import LLMClient
from schemas.director import Message
from schemas.stage import load_stage_profile_by_id
from schemas.student import load_personas


async def main() -> None:
    stage = load_stage_profile_by_id("p_lower")
    if stage is None:
        raise RuntimeError("未找到 p_lower stage profile")
    students = load_personas()[:5]
    print(f"📂 加载 {len(students)} 名学生，学段={stage.id} {stage.name}")

    llm = LLMClient()
    print(f"✅ LLMClient 初始化成功 (model={llm.model})")
    print(f"📡 base_url={llm.base_url}\n")

    agent = DirectorAgent(llm=llm)
    history = [Message(role="teacher", speaker_id="teacher", content="今天我们学习分数。", timestamp_seconds=0)]
    decision = await agent.decide("同学们，谁来说说 1/2 表示什么？", stage, students, history, 30)

    print("actions:")
    for action in decision.actions:
        print(f"- {action.speaker_id}: {action.action_type} priority={action.priority}")
    print(f"delay: {decision.next_action_delay_ms} ms")
    print(f"rationale: {decision.rationale}")


if __name__ == "__main__":
    asyncio.run(main())
