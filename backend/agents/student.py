"""StudentAgent — 单学生虚拟角色（1v1 答疑陪练专用）。

该 agent 提供两个能力：

1. ``generate_questions(lesson_meta)``
   根据人设 + 教案 + 学段迷思库，主动提出学生会问老师的问题。输出为
   ``list[StudentQuestion]``，含 category / difficulty / linked_key_point /
   linked_misconception_id 等结构化元数据。

2. ``respond_in_dialog(question, teacher_utterance, history)``
   在 1v1 对话中根据老师发言多轮回应。输出为 ``DialogReplyResult``（
   含是否出现 ``[懂了]`` 标记的 ``self_resolved`` 字段）。

人设支持：
- 简易模式（name / personality / knowledge_level / behavior_traits）
- 完整模式（从 data/personas/*.json 加载，18 字段）

老课堂回合制 ``respond()`` 接口已随产品转型废弃，详见 ``docs/PIVOT.md``。

典型用法::

    from agents.student import StudentAgent
    from llm.client import LLMClient

    agent = StudentAgent(llm=LLMClient(), persona=persona, stage=stage)
    qs = await agent.generate_questions(lesson_meta, count=3)
    result = await agent.respond_in_dialog(question=qs[0], teacher_utterance="...")
    print(result.content, result.self_resolved)
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
from schemas.student import ClassroomContext, Persona

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


class StudentAgent:
    """单学生 Agent。1v1 答疑陪练中的虚拟学生角色。

    Parameters
    ----------
    llm : LLMClient
        已配置好的 LLM 客户端（默认 ChatECNU ecnu-max）。
    persona : Persona
        学生人设，支持简易模式或 data/personas/ 完整 JSON。
    stage : StageProfile | None
        可选的学段共性特征。传入后会在 prompt 顶部注入认知边界。
        不传则仅依赖个体 persona。
    temperature : float
        LLM 采样温度，默认 0.8。
    misconceptions / misconceptions_dir
        迷思库来源。不传则从项目默认 ``data/misconceptions/`` 加载。
    rng : random.Random | None
        仅供未来需要随机采样的场景使用（如随机选择迷思）。
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        persona: Persona,
        stage: StageProfile | None = None,
        temperature: float = 0.8,
        misconceptions: list[Misconception] | None = None,
        misconceptions_dir: str | Path | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.llm = llm
        self.persona = persona
        self.stage = stage
        self.temperature = temperature
        self.misconceptions = (
            misconceptions
            if misconceptions is not None
            else load_misconceptions(misconceptions_dir)
        )
        self.rng = rng or random.Random()
        self._ask_template = _jinja_env.get_template("student_ask.j2")
        self._chat_template = _jinja_env.get_template("student_chat.j2")

    # =========================================================== public

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
