"""StudentAgent — 单学生虚拟角色。

根据人设 (Persona) + 课堂上下文 (ClassroomContext) + 老师最新发言，
调用 LLM 生成结构化的 StudentReply。

典型用法::

    from agents.student import StudentAgent
    from llm.client import LLMClient
    from schemas.student import ClassroomContext, Persona

    agent = StudentAgent(llm=LLMClient(), persona=persona, context=context)
    reply = await agent.respond("什么是分数？")
    print(reply)  # StudentReply(speaker_id=..., intent=..., content=..., emotion=...)
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from llm.client import LLMClient
from schemas.student import ClassroomContext, Persona, StudentReply

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


class StudentAgent:
    """单学生 Agent。

    Parameters
    ----------
    llm : LLMClient
        已配置好的 LLM 客户端。
    persona : Persona
        学生人设。
    context : ClassroomContext
        当前课堂上下文（可在对话过程中更新）。
    temperature : float
        LLM 采样温度，默认 0.8 以增加回复多样性。
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        persona: Persona,
        context: ClassroomContext,
        temperature: float = 0.8,
    ) -> None:
        self.llm = llm
        self.persona = persona
        self.context = context
        self.temperature = temperature
        self._template = _jinja_env.get_template("student.j2")

    # -------------------------------------------------------------- public

    async def respond(self, teacher_utterance: str) -> StudentReply:
        """根据老师的发言生成学生回复。

        Returns
        -------
        StudentReply
            包含 speaker_id / intent / content / emotion 的结构化回复。
        """
        prompt = self._render_prompt(teacher_utterance)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": teacher_utterance},
        ]

        resp = await self.llm.chat(messages, temperature=self.temperature)
        raw = resp.choices[0].message.content or ""

        logger.debug("StudentAgent raw LLM output: %s", raw)

        reply = self._parse_reply(raw)

        # 追加到课堂历史
        self.context.history.append(f"老师：{teacher_utterance}")
        self.context.history.append(f"{reply.speaker_id}：{reply.content}")

        return reply

    # ------------------------------------------------------------- private

    def _render_prompt(self, teacher_utterance: str) -> str:
        return self._template.render(
            persona=self.persona,
            context=self.context,
            teacher_utterance=teacher_utterance,
        )

    def _parse_reply(self, raw: str) -> StudentReply:
        """从 LLM 原始输出中提取 JSON 并解析为 StudentReply。

        支持 LLM 输出被 ```json ... ``` 包裹或直接输出 JSON 的情况。
        """
        # 尝试提取 markdown code block 中的 JSON
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # 直接尝试找第一个 { ... }
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                logger.warning(
                    "StudentAgent: no JSON found in LLM output, building fallback reply"
                )
                return StudentReply(
                    speaker_id=self.persona.name,
                    intent="passive",
                    content=raw.strip() or "……",
                    emotion="困惑",
                )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("StudentAgent: invalid JSON: %s", json_str[:200])
            return StudentReply(
                speaker_id=self.persona.name,
                intent="passive",
                content=raw.strip() or "……",
                emotion="困惑",
            )

        # 校验 intent 合法性
        valid_intents = {"answer_question", "ask_question", "off_topic", "passive"}
        if data.get("intent") not in valid_intents:
            data["intent"] = "passive"

        # 确保 speaker_id
        data.setdefault("speaker_id", self.persona.name)
        data.setdefault("emotion", "平静")

        return StudentReply(**data)
