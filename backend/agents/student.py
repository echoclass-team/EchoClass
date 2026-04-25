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
import uuid
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from llm.client import LLMClient
from rag.misconceptions import load_misconceptions, match_misconceptions
from schemas.dialog import DialogMessage, DialogReplyResult
from schemas.lesson import LessonMeta
from schemas.misconception import Misconception
from schemas.question import StudentQuestion
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
        self._ask_template = _jinja_env.get_template("student_ask.j2")
        self._chat_template = _jinja_env.get_template("student_chat.j2")

    # -------------------------------------------------------------- public

    async def respond(self, teacher_utterance: str) -> StudentReply:
        """根据老师的发言生成学生回复。

        Returns
        -------
        StudentReply
            包含 speaker_id / intent / content / emotion 的结构化回复。
        """
        matched_misconceptions = self._match_misconceptions()
        triggered_misconception = self._choose_triggered_misconception(
            matched_misconceptions
        )
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

    def _choose_triggered_misconception(
        self, matched: list[Misconception]
    ) -> Misconception | None:
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

    # =========================================================== Q/A coach
    # 以下方法服务于"1v1 答疑陪练"新方向（详见 docs/PIVOT.md）。
    # 与上面的回合制 ``respond`` 完全独立，不共用 prompt 模板。

    async def generate_questions(
        self,
        lesson_meta: LessonMeta,
        *,
        count: int = 3,
    ) -> list[StudentQuestion]:
        """根据教案 + 自身人设生成一组学生想问的问题。

        典型用法（在 1v1 答疑陪练入口）::

            qs = await agent.generate_questions(lesson_meta, count=3)
            for q in qs:
                print(q.category, q.difficulty, q.content)

        Parameters
        ----------
        lesson_meta : LessonMeta
            已解析的教案元数据（含 subject / topic / key_points / difficult_points）。
        count : int
            希望生成几个问题，默认 3。LLM 实际产出可能多/少，方法内会裁剪到 ≤count。

        Returns
        -------
        list[StudentQuestion]
            每个问题已带稳定的 ``id``（uuid4）、``speaker_id``、``speaker_name``。
            非法的 category / difficulty / linked_misconception_id 会被规范化或剔除。
        """
        if count < 1:
            return []

        ctx = self._lesson_to_context(lesson_meta)
        matched = self._match_misconceptions_for_lesson(ctx)
        prompt = self._ask_template.render(
            persona=self.persona,
            stage=self.stage,
            context=ctx,
            matched_misconceptions=matched,
            question_count=count,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请输出 JSON 数组。"},
        ]
        resp = await self.llm.chat(messages, temperature=self.temperature)
        raw = resp.choices[0].message.content or ""
        logger.debug("StudentAgent.generate_questions raw: %s", raw)

        items = self._parse_question_array(raw)
        valid_misconception_ids = {m.id for m in matched}
        questions: list[StudentQuestion] = []
        for item in items[:count]:
            try:
                question = self._build_question(
                    item,
                    valid_key_points=set(lesson_meta.key_points)
                    | set(lesson_meta.difficult_points),
                    valid_misconception_ids=valid_misconception_ids,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "StudentAgent.generate_questions skip invalid item: %s (%s)",
                    item,
                    exc,
                )
                continue
            questions.append(question)
        return questions

    async def respond_in_dialog(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history: list[DialogMessage] | None = None,
    ) -> DialogReplyResult:
        """1v1 答疑陪练里的一轮回应。

        与回合制 ``respond`` 不同：
        - 输入是单一 ``StudentQuestion``（而非整堂课上下文）+ 对话历史
        - 输出是**纯文本**学生话语（而非含 intent/emotion 的 JSON）
        - 检测末尾 ``[懂了]`` 标记 → ``self_resolved=True``，由上游 orchestrator 决定是否结束会话

        Parameters
        ----------
        question : StudentQuestion
            本次答疑会话的入口问题（学生最初提的）。
        teacher_utterance : str
            老师本轮的解答 / 追问发言。
        dialog_history : list[DialogMessage] | None
            到本轮为止的对话历史（不含 question 本身、不含本轮 teacher_utterance）。

        Returns
        -------
        DialogReplyResult
            ``content`` 已剥离 ``[懂了]`` 标记，``self_resolved`` 反映该标记是否出现。
        """
        prompt = self._chat_template.render(
            persona=self.persona,
            stage=self.stage,
            question=question,
            dialog_history=dialog_history or [],
            teacher_utterance=teacher_utterance,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": teacher_utterance},
        ]
        resp = await self.llm.chat(messages, temperature=self.temperature)
        raw = resp.choices[0].message.content or ""
        logger.debug("StudentAgent.respond_in_dialog raw: %s", raw)
        return self._parse_dialog_reply(raw)

    # ---------------------------------------------------- Q/A coach helpers

    def _lesson_to_context(self, lesson_meta: LessonMeta) -> ClassroomContext:
        """把 LessonMeta 适配成 prompt 模板用的 ClassroomContext。"""
        return ClassroomContext(
            subject=lesson_meta.subject,
            topic=lesson_meta.topic,
            history=[],
            key_points=list(lesson_meta.key_points),
            difficult_points=list(lesson_meta.difficult_points),
        )

    def _match_misconceptions_for_lesson(
        self, ctx: ClassroomContext
    ) -> list[Misconception]:
        stage_id = self.stage.id if self.stage is not None else self.persona.stage_id
        return match_misconceptions(
            subject=ctx.subject,
            stage_id=stage_id,
            key_points=ctx.key_points,
            topic=ctx.topic,
            difficult_points=ctx.difficult_points,
            misconceptions=self.misconceptions,
        )

    def _parse_question_array(self, raw: str) -> list[dict[str, Any]]:
        """从 LLM 输出抽取 JSON 数组；兼容 ```json``` 包裹与裸数组。"""
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
        candidate = match.group(1) if match else None
        if candidate is None:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            candidate = match.group(0) if match else None
        if candidate is None:
            logger.warning("StudentAgent.generate_questions: no JSON array in output")
            return []
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.warning(
                "StudentAgent.generate_questions: invalid JSON (%s): %s",
                exc,
                candidate[:200],
            )
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    _VALID_CATEGORIES: frozenset[str] = frozenset(
        {
            "clarify_concept",
            "challenge_example",
            "extend_topic",
            "off_topic",
            "stuck_misconception",
        }
    )
    _VALID_DIFFICULTIES: frozenset[str] = frozenset({"easy", "medium", "hard"})

    def _build_question(
        self,
        item: dict[str, Any],
        *,
        valid_key_points: set[str],
        valid_misconception_ids: set[str],
    ) -> StudentQuestion:
        content = str(item.get("content", "")).strip()
        if not content:
            raise ValueError("empty content")

        category = item.get("category")
        if category not in self._VALID_CATEGORIES:
            category = "clarify_concept"

        difficulty = item.get("difficulty")
        if difficulty not in self._VALID_DIFFICULTIES:
            difficulty = "medium"

        linked_kp = item.get("linked_key_point")
        if linked_kp is not None:
            linked_kp = str(linked_kp).strip() or None
            if linked_kp and linked_kp not in valid_key_points:
                # LLM 自由发挥的非教案重点字符串，为避免污染评估，置空
                linked_kp = None

        linked_mid = item.get("linked_misconception_id")
        if linked_mid is not None:
            linked_mid = str(linked_mid).strip() or None
            if linked_mid and linked_mid not in valid_misconception_ids:
                linked_mid = None
        # category 与 misconception 关联性约束：只有这两类才允许带迷思
        if category not in {"stuck_misconception", "challenge_example"}:
            linked_mid = None

        rationale = str(item.get("rationale", "")).strip()

        return StudentQuestion(
            id=str(uuid.uuid4()),
            speaker_id=self.persona.id or self.persona.name,
            speaker_name=self.persona.name,
            content=content,
            category=category,  # type: ignore[arg-type]
            difficulty=difficulty,  # type: ignore[arg-type]
            linked_key_point=linked_kp,
            linked_misconception_id=linked_mid,
            rationale=rationale,
        )

    _RESOLVE_MARKER_RE = re.compile(r"\[\s*懂了\s*\]\s*$")

    def _parse_dialog_reply(self, raw: str) -> DialogReplyResult:
        text = raw.strip()
        self_resolved = bool(self._RESOLVE_MARKER_RE.search(text))
        if self_resolved:
            text = self._RESOLVE_MARKER_RE.sub("", text).rstrip()
        if not text:
            text = "……"
        return DialogReplyResult(content=text, self_resolved=self_resolved, raw=raw)
