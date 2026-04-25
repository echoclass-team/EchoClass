"""StudentAgent — 单学生虚拟角色。

根据人设 (Persona) + 课堂上下文 (ClassroomContext) + 老师最新发言，
通过 LLMClient 调用 ChatECNU ecnu-max 生成结构化的 StudentReply。

人设支持两种模式：
- 简易模式：4 个基础字段（name / personality / knowledge_level / behavior_traits）
- 完整模式：从 data/personas/*.json 加载的18 字段人设（含口头禅、迷思概念、认知阶段等）

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
import random
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from llm.client import LLMClient
from rag.misconceptions import load_misconceptions, match_misconceptions
from schemas.misconception import Misconception
from schemas.stage import StageProfile
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

    每个实例代表一个虚拟学生，通过 Jinja2 模板渲染 Prompt 并调用 LLM 生成符合人设的回复。
    回复为结构化 JSON，包含意图 (intent)、内容 (content)、情绪 (emotion)。

    Parameters
    ----------
    llm : LLMClient
        已配置好的 LLM 客户端（默认 ChatECNU ecnu-max）。
    persona : Persona
        学生人设，支持简易模式或 data/personas/ 完整 JSON。
    context : ClassroomContext
        当前课堂上下文（对话过程中自动追加历史记录）。
    stage : StageProfile | None
        可选的学段共性特征。传入后会在 prompt 顶部注入学段认知天花板，
        约束 LLM 的回复不超出该年龄段能力。不传则仅依赖个体 persona。
    temperature : float
        LLM 采样温度，默认 0.8 以增加回复多样性。
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        persona: Persona,
        context: ClassroomContext,
        stage: StageProfile | None = None,
        temperature: float = 0.8,
        misconceptions: list[Misconception] | None = None,
        misconceptions_dir: str | Path | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.llm = llm
        self.persona = persona
        self.context = context
        self.stage = stage
        self.temperature = temperature
        self.misconceptions = (
            misconceptions
            if misconceptions is not None
            else load_misconceptions(misconceptions_dir)
        )
        self.rng = rng or random.Random()
        self._template = _jinja_env.get_template("student.j2")

    # -------------------------------------------------------------- public

    async def respond(self, teacher_utterance: str) -> StudentReply:
        """根据老师的发言生成学生回复。

        Returns
        -------
        StudentReply
            包含 speaker_id / intent / content / emotion 的结构化回复。
        """
        matched_misconceptions = self._match_misconceptions()
        triggered_misconception = self._choose_triggered_misconception(matched_misconceptions)
        prompt = self._render_prompt(
            teacher_utterance,
            matched_misconceptions=matched_misconceptions,
            triggered_misconception=triggered_misconception,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": teacher_utterance},
        ]

        resp = await self.llm.chat(messages, temperature=self.temperature)
        raw = resp.choices[0].message.content or ""

        logger.debug("StudentAgent raw LLM output: %s", raw)

        reply = self._parse_reply(raw)
        reply = self._normalize_triggered_misconception(
            reply,
            matched_misconceptions=matched_misconceptions,
            triggered_misconception=triggered_misconception,
        )

        # 追加到课堂历史
        self.context.history.append(f"老师：{teacher_utterance}")
        self.context.history.append(f"{reply.speaker_id}：{reply.content}")

        return reply

    # ------------------------------------------------------------- private

    def _render_prompt(
        self,
        teacher_utterance: str,
        *,
        matched_misconceptions: list[Misconception] | None = None,
        triggered_misconception: Misconception | None = None,
    ) -> str:
        return self._template.render(
            persona=self.persona,
            context=self.context,
            stage=self.stage,
            teacher_utterance=teacher_utterance,
            matched_misconceptions=matched_misconceptions or [],
            triggered_misconception=triggered_misconception,
        )

    def _match_misconceptions(self) -> list[Misconception]:
        stage_id = self.stage.id if self.stage is not None else self.persona.stage_id
        return match_misconceptions(
            subject=self.context.subject,
            stage_id=stage_id,
            key_points=self.context.key_points,
            topic=self.context.topic,
            difficult_points=self.context.difficult_points,
            misconceptions=self.misconceptions,
        )

    def _choose_triggered_misconception(self, matched: list[Misconception]) -> Misconception | None:
        if not matched:
            return None
        probability = self._trigger_probability()
        if self.rng.random() < probability:
            return matched[0]
        return None

    def _trigger_probability(self) -> float:
        level = self.persona.effective_level.lower()
        if "薄弱" in level or "weak" in level:
            return 0.5
        if "优秀" in level or "优等" in level or "strong" in level or "xueba" in level:
            return 0.05
        if "中等" in level or "medium" in level:
            return 0.25
        return 0.25

    def _normalize_triggered_misconception(
        self,
        reply: StudentReply,
        *,
        matched_misconceptions: list[Misconception],
        triggered_misconception: Misconception | None,
    ) -> StudentReply:
        if triggered_misconception is None:
            reply.triggered_misconception_id = None
            return reply
        if reply.intent == "answer_question":
            reply.triggered_misconception_id = triggered_misconception.id
        else:
            reply.triggered_misconception_id = None
        return reply

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
