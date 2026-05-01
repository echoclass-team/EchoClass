"""StudentAgent — 单学生虚拟角色（1v1 / M3 连续答疑陪练专用）。

该 agent 提供四个能力：

1. ``generate_questions(lesson_meta)``
   根据人设 + 教案 + 学段迷思库，主动提出学生会问老师的问题。输出为
   ``list[StudentQuestion]``，含 category / difficulty / linked_key_point /
   linked_misconception_id 等结构化元数据。

2. ``respond_in_dialog(question, teacher_utterance, history)``
   在1v1 对话中根据老师发言多轮回应。输出为 ``DialogReplyResult``（
   含是否出现 ``[懂了]`` 标记的 ``self_resolved`` 字段）。

3. ``stream_in_dialog(...)``
   ``respond_in_dialog`` 的流式版本，逐 token 推送 ``StudentStreamEvent``：
   先若干 ``delta`` 事件（已剥离末尾 ``[懂了]`` 标记），最后一个 ``final``
   事件携带完整 ``DialogReplyResult``。供 WebSocket 端点直接转发。

4. ``decide_followup(...)``【M3 / #111】
   每轮老师消息 → 学生回复后，LLM 决策学生是否主动追问。输出为
   ``FollowupDecision``（含 ``should_followup`` / ``new_question`` / ``reason``）。
   解析失败会优雅降级为 ``no_followup``，不抛出异常。

人设支持：
- 简易模式（name / personality / knowledge_level / behavior_traits）
- 完整模式（从 data/personas/*.json 加载，18 字段）

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
from rag.qa_examples import (
    load_qa_examples,
    select_ask_examples,
    select_chat_examples,
)
from schemas.dialog import DialogMessage, DialogReplyResult, StudentStreamEvent
from schemas.followup import FollowupDecision
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
        qa_examples_dir: str | Path | None = None,
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
        self.qa_examples_dir = qa_examples_dir
        self.rng = rng or random.Random()
        self._ask_template = _jinja_env.get_template("student_ask.j2")
        self._chat_template = _jinja_env.get_template("student_chat.j2")
        self._check_template = _jinja_env.get_template("student_check.j2")
        self._followup_template = _jinja_env.get_template("student_followup.j2")

    # =========================================================== public

    async def generate_questions(
        self,
        lesson_meta: LessonMeta,
        *,
        count: int = 3,
        overshoot: int = 3,
        self_check: bool = True,
    ) -> list[StudentQuestion]:
        """根据教案 + 自身人设生成一组学生想问的问题（宽生成 + self-check + 多样性筛选）。

        流程::

            1. 第一次 LLM：用 student_ask.j2 生成 count + overshoot 个候选
            2. 解析校验为 list[StudentQuestion]
            3. 第二次 LLM（可选）：用 student_check.j2 让 agent 自评每条候选
            4. 类别多样性 + 自评分综合排序，取 top count

        Parameters
        ----------
        lesson_meta : LessonMeta
            已解析的教案元数据。
        count : int
            最终返回的问题数量。
        overshoot : int
            宽生成时多生成 overshoot 个候选，给 self-check 留挑选空间。
            建议 ≥ 2，越大质量越高但 LLM 成本越高。
        self_check : bool
            是否启用二阶段 self-check。关闭时方法只走第一次 LLM 调用，
            返回前 ``count`` 个合法候选（行为同 M1 之前）。

        Returns
        -------
        list[StudentQuestion]
            带 ``id`` / ``speaker_id`` / ``speaker_name`` 的合法问题；启用 self_check
            时同时填充 ``self_score``。返回顺序按"类别多样性 + self_score 降序"排列。
        """
        if count < 1:
            return []

        # ---- 第一阶段：宽生成
        ctx = self._lesson_to_context(lesson_meta)
        matched = self._match_misconceptions_for_lesson(ctx)
        ask_examples = self._select_ask_examples()
        target_count = count + max(overshoot, 0) if self_check else count
        prompt = self._ask_template.render(
            persona=self.persona,
            stage=self.stage,
            context=ctx,
            matched_misconceptions=matched,
            question_count=target_count,
            ask_examples=ask_examples,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"请输出 {target_count} 个候选问题的 JSON 数组。",
            },
        ]
        resp = await self.llm.chat(messages, temperature=self.temperature)
        raw = resp.choices[0].message.content or ""
        logger.debug("StudentAgent.generate_questions raw: %s", raw)

        items = self._parse_question_array(raw)
        valid_misconception_ids = {m.id for m in matched}
        candidates: list[StudentQuestion] = []
        for item in items[:target_count]:
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
            candidates.append(question)

        if not candidates:
            return []

        # ---- 第二阶段：self-check（可选）
        if self_check and len(candidates) > 1:
            try:
                await self._apply_self_check(candidates, ctx)
            except Exception as exc:  # noqa: BLE001 - self-check 失败应降级而非拖累生成
                logger.warning(
                    "StudentAgent.generate_questions self-check failed (%s); fallback to no-score order",
                    exc,
                )

        # ---- 多样性筛选 + 排序
        return self._select_diverse(candidates, count=count)

    async def respond_in_dialog(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history: list[DialogMessage] | None = None,
    ) -> DialogReplyResult:
        """1v1 答疑陪练里的一轮回应。

        - 输入是单一 ``StudentQuestion`` + 对话历史
        - 输出是**纯文本**学生话语，末尾可能含 ``[懂了]`` 标记
        - 检测末尾 ``[懂了]`` → ``self_resolved=True``，由上游 orchestrator 决定是否结束会话

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
        messages = self._build_chat_messages(
            question=question,
            teacher_utterance=teacher_utterance,
            dialog_history=dialog_history,
        )
        resp = await self.llm.chat(messages, temperature=self.temperature)
        raw = resp.choices[0].message.content or ""
        logger.debug("StudentAgent.respond_in_dialog raw: %s", raw)
        return self._parse_dialog_reply(raw)

    async def stream_in_dialog(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history: list[DialogMessage] | None = None,
    ):
        """``respond_in_dialog`` 的流式版本：逐 token 推送 ``StudentStreamEvent``。

        事件序列::

            delta(text=...)     # 0..N 个，按 LLM 增量分片推送
            ...
            final(result=DialogReplyResult)   # 总最后一个

        关键行为：
        - delta 推送时会保留尾部 ``HOLDBACK`` 个字符不发，避免把可能成为
          ``[懂了]`` 标记的尾巴提前 emit 到前端
        - 流结束时用 ``_parse_dialog_reply`` 处理完整原文，得到剥离标记后的
          ``content`` 与 ``self_resolved``；若 final.content 还有未推送的尾部，
          会先补一个 ``delta`` 事件，再推 ``final``
        - LLM 上游异常会原地抛出，由调用方处理

        Yields
        ------
        StudentStreamEvent
        """
        messages = self._build_chat_messages(
            question=question,
            teacher_utterance=teacher_utterance,
            dialog_history=dialog_history,
        )

        accumulated = ""
        emitted_len = 0
        holdback = self._STREAM_HOLDBACK_CHARS

        async for chunk in self.llm.stream(messages, temperature=self.temperature):
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta_obj = getattr(choices[0], "delta", None)
            piece = getattr(delta_obj, "content", None) if delta_obj else None
            if not piece:
                continue
            accumulated += piece
            safe_len = max(emitted_len, len(accumulated) - holdback)
            if safe_len > emitted_len:
                yield StudentStreamEvent(
                    type="delta",
                    delta=accumulated[emitted_len:safe_len],
                )
                emitted_len = safe_len

        logger.debug("StudentAgent.stream_in_dialog raw: %s", accumulated)
        final = self._parse_dialog_reply(accumulated)

        # 已 emit 的是 raw 前缀，final.content 是 strip + 剥离标记后的版本。
        # 若 final.content 仍以已 emit 的文本为前缀，把剩余部分作为最后一个 delta 推出，
        # 让前端在 final 到达前已渲染到完整可见文本，减少跳变。
        already_emitted = accumulated[:emitted_len]
        if final.content.startswith(already_emitted):
            tail = final.content[len(already_emitted) :]
            if tail:
                yield StudentStreamEvent(type="delta", delta=tail)

        yield StudentStreamEvent(type="final", result=final)

    async def decide_followup(
        self,
        *,
        current_question: StudentQuestion,
        dialog_history: list[DialogMessage],
        lesson_meta: LessonMeta,
        asked_questions: list[StudentQuestion] | None = None,
    ) -> FollowupDecision:
        """每轮老师消息 → 学生回复后，决策学生是否主动追问（M3 / #111）。

        Parameters
        ----------
        current_question : StudentQuestion
            当前正在讨论的问题（最近一次抛出的，可能是首问或之前的追问）。
        dialog_history : list[DialogMessage]
            到本轮为止的完整对话历史（含本轮 student 回复）。
        lesson_meta : LessonMeta
            教案上下文，用于约束追问内容不跑题。
        asked_questions : list[StudentQuestion] | None
            本 dialog 中已经问过的所有问题（含 current_question）；用于在
            prompt 中提示"禁止重复"，并在结果上做一次 content 文本重复过滤。
            缺省时按 ``[current_question]`` 处理。

        Returns
        -------
        FollowupDecision
            ``should_followup=False`` 时不追问；True 时附带新生成的
            ``StudentQuestion``（含 id / speaker_* 等完整字段）。

        Notes
        -----
        解析失败 / Schema 不合法 / LLM 上游异常都会**优雅降级**为
        ``FollowupDecision.no_followup(reason=...)``，**不向上抛出**。
        这样上层编排（``QASession``）即便单次 LLM 抖动也不会被卡死，
        仅本轮没有追问，下轮仍会再次询问 LLM。
        """
        asked = asked_questions if asked_questions is not None else [current_question]

        prompt = self._followup_template.render(
            persona=self.persona,
            stage=self.stage,
            lesson=lesson_meta,
            current_question=current_question,
            dialog_history=dialog_history or [],
            asked_questions=asked,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请输出决策 JSON。"},
        ]
        try:
            # 决策类任务，温度低些减少抖动
            resp = await self.llm.chat(
                messages, temperature=max(0.3, self.temperature - 0.3)
            )
        except Exception as exc:  # noqa: BLE001 - 上游抖动应降级而非阻塞编排
            logger.warning("StudentAgent.decide_followup LLM call failed: %s", exc)
            return FollowupDecision.no_followup(reason=f"llm_error: {exc}")

        raw = resp.choices[0].message.content or ""
        logger.debug("StudentAgent.decide_followup raw: %s", raw)

        return self._parse_followup_decision(
            raw,
            valid_key_points=set(lesson_meta.key_points)
            | set(lesson_meta.difficult_points),
            asked_question_contents={q.content.strip() for q in asked},
        )

    def _parse_followup_decision(
        self,
        raw: str,
        *,
        valid_key_points: set[str],
        asked_question_contents: set[str],
    ) -> FollowupDecision:
        """从 LLM 输出解析 FollowupDecision；任何错误均降级为 no_followup。"""
        obj = self._extract_json_object(raw)
        if obj is None:
            return FollowupDecision.no_followup(reason="parse_error: no JSON object")

        should = bool(obj.get("should_followup", False))
        reason = str(obj.get("reason", "")).strip()

        if not should:
            return FollowupDecision.no_followup(reason=reason or "decided not to ask")

        new_q_data = obj.get("new_question")
        if not isinstance(new_q_data, dict):
            return FollowupDecision.no_followup(
                reason="parse_error: should_followup=true but new_question missing"
            )

        try:
            new_question = self._build_question(
                new_q_data,
                valid_key_points=valid_key_points,
                # 追问场景不强约束 misconception 关联（LLM 给了也会被忽略）
                valid_misconception_ids=set(),
            )
        except Exception as exc:  # noqa: BLE001
            return FollowupDecision.no_followup(
                reason=f"parse_error: invalid new_question ({exc})"
            )

        # 文本级重复检测：若新问题与任一已问过的内容文本一致，降级
        if new_question.content.strip() in asked_question_contents:
            return FollowupDecision.no_followup(
                reason="duplicate: new_question matches an asked question"
            )

        return FollowupDecision(
            should_followup=True,
            new_question=new_question,
            reason=reason or "follow-up generated",
        )

    @staticmethod
    def _extract_json_object(raw: str) -> dict[str, Any] | None:
        """从 LLM 输出抽取 JSON 对象；兼容 ``` 包裹与裸 ``{...}``。"""
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        candidate = match.group(1) if match else None
        if candidate is None:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            candidate = match.group(0) if match else None
        if candidate is None:
            return None
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.warning(
                "StudentAgent JSON object parse failed (%s): %s",
                exc,
                candidate[:200],
            )
            return None
        return data if isinstance(data, dict) else None

    # 流式 hold-back 长度：[懂了] / [ 懂了 ] / 末尾换行最长 ~ 12 字符，留 16 安全冗余
    _STREAM_HOLDBACK_CHARS: int = 16

    def _build_chat_messages(
        self,
        *,
        question: StudentQuestion,
        teacher_utterance: str,
        dialog_history: list[DialogMessage] | None,
    ) -> list[dict[str, Any]]:
        """渲染 student_chat.j2 prompt 并拼装 chat messages（共享给同步/流式）。"""
        chat_examples = self._select_chat_examples()
        resolved_theories = self._resolve_theory_anchors()
        prompt = self._chat_template.render(
            persona=self.persona,
            stage=self.stage,
            question=question,
            dialog_history=dialog_history or [],
            teacher_utterance=teacher_utterance,
            chat_examples=chat_examples,
            resolved_theories=resolved_theories,
        )
        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": teacher_utterance},
        ]

    def _resolve_theory_anchors(self):
        """把 ``persona.theory_anchors`` 解析为 ``ResolvedTheory`` 列表。

        POC 阶段：失败时安静 fallback 为空列表（不阻塞主流程）。
        生产路径如果出错应该被监控告警，但这里 POC 优先稳定性。
        """
        if not getattr(self.persona, "theory_anchors", None):
            return []
        try:
            from kb.poc_loader import resolve_persona_anchors

            return resolve_persona_anchors(self.persona)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to resolve theory anchors for persona %s: %s",
                self.persona.name,
                exc,
            )
            return []

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

    def _resolve_stage_id(self) -> str:
        """优先使用 self.stage.id，否则回退到 persona.stage_id。"""
        return self.stage.id if self.stage is not None else self.persona.stage_id

    def _select_ask_examples(self):
        """加载并按当前 persona 挑选 ask 类 few-shot；学段缺失则返回空列表。"""
        stage_id = self._resolve_stage_id()
        if not stage_id:
            return []
        examples = load_qa_examples(stage_id, self.qa_examples_dir)
        return select_ask_examples(
            examples,
            persona_level=self.persona.effective_level,
            persona_tag_hint="",
            max_count=2,
        )

    def _select_chat_examples(self):
        """加载并按当前 persona 挑选 chat 类 few-shot；学段缺失则返回空列表。"""
        stage_id = self._resolve_stage_id()
        if not stage_id:
            return []
        examples = load_qa_examples(stage_id, self.qa_examples_dir)
        return select_chat_examples(
            examples,
            persona_level=self.persona.effective_level,
            persona_tag_hint="",
            max_count=1,
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

    # ----------------------------------------------------- self-check helpers

    async def _apply_self_check(
        self,
        candidates: list[StudentQuestion],
        ctx: ClassroomContext,
    ) -> None:
        """让 agent 第二次调 LLM 自评 candidates，原地写回 ``self_score`` 并剔除 keep=false。

        失败时调用方会捕获异常并降级——保留原顺序、不写 self_score。
        本方法**就地修改** candidates（删掉 keep=false 的元素，并设置 self_score）。
        """
        prompt = self._check_template.render(
            persona=self.persona,
            stage=self.stage,
            context=ctx,
            candidates=candidates,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请输出 JSON 数组。"},
        ]
        # self-check 期望更稳定的判断，温度可低些，但仍需保留多样性
        resp = await self.llm.chat(
            messages, temperature=max(0.2, self.temperature - 0.3)
        )
        raw = resp.choices[0].message.content or ""
        logger.debug("StudentAgent.self_check raw: %s", raw)

        verdicts = self._parse_self_check_array(raw, expected_len=len(candidates))
        if not verdicts:
            logger.warning("self-check 未返回有效 verdicts，降级保留全部 candidates")
            return

        # index → verdict 映射，保护后续筛选不依赖输出顺序
        verdict_map = {v["index"]: v for v in verdicts if "index" in v}
        kept: list[StudentQuestion] = []
        for i, q in enumerate(candidates):
            v = verdict_map.get(i)
            if v is None:
                # 缺评分的候选保留但标记为最低有效分
                q.self_score = 50.0
                kept.append(q)
                continue
            score = float(v.get("score", 50))
            score = max(0.0, min(100.0, score))
            q.self_score = score
            keep_flag = v.get("keep")
            # 显式 false 才剔除；缺省视为保留
            if keep_flag is False or score < 40:
                continue
            kept.append(q)

        # 至少保留 1 条避免 0 候选
        if not kept and candidates:
            kept = sorted(
                candidates,
                key=lambda q: q.self_score if q.self_score is not None else -1,
                reverse=True,
            )[:1]

        candidates.clear()
        candidates.extend(kept)

    @staticmethod
    def _parse_self_check_array(raw: str, expected_len: int) -> list[dict[str, Any]]:
        """从 LLM 自评输出抽取 JSON 数组；兼容 ``` 包裹与裸数组。"""
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
        candidate = match.group(1) if match else None
        if candidate is None:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            candidate = match.group(0) if match else None
        if candidate is None:
            return []
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            logger.warning("self-check JSON 解析失败 (%s): %s", exc, candidate[:200])
            return []
        if not isinstance(data, list):
            return []
        return [v for v in data if isinstance(v, dict)]

    @staticmethod
    def _select_diverse(
        candidates: list[StudentQuestion],
        *,
        count: int,
    ) -> list[StudentQuestion]:
        """按"类别多样性优先 + self_score 降序"筛选 top count。

        贪心策略：
        1. 候选先按 self_score 降序排（None 视为 0）
        2. 依次取，遇到已出现过的 category 就先跳过
        3. 第一轮拿不满 count 时，再不限 category 取剩下高分的
        """
        if count <= 0 or not candidates:
            return []
        sorted_pool = sorted(
            candidates,
            key=lambda q: q.self_score if q.self_score is not None else 0.0,
            reverse=True,
        )
        seen_categories: set[str] = set()
        first_pass: list[StudentQuestion] = []
        leftover: list[StudentQuestion] = []
        for q in sorted_pool:
            if len(first_pass) >= count:
                leftover.append(q)
                continue
            if q.category in seen_categories:
                leftover.append(q)
                continue
            first_pass.append(q)
            seen_categories.add(q.category)

        result = first_pass[:count]
        for q in leftover:
            if len(result) >= count:
                break
            result.append(q)
        return result
