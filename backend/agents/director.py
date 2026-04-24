"""DirectorAgent — 多学生课堂调度器。

DirectorAgent 负责在 3-8 人虚拟课堂中决定下一刻学生动作。它采用
"规则层硬约束 + LLM 层软判断" 的结构：规则层保证点名、冷却、配额、学段
节奏等约束不被破坏；LLM 层只补充是否插入举手、发言、走神或沉默等情境判断。
"""

from __future__ import annotations

import inspect
import json
import logging
import random
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from llm.client import LLMClient
from schemas.director import DirectorConfig, DirectorDecision, Message, StudentAction
from schemas.stage import StageProfile
from schemas.student import Persona

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


class DirectorAgent:
    """学段感知的多学生调度器。

    Parameters
    ----------
    llm : LLMClient
        已配置好的 LLM 客户端。
    config : DirectorConfig | None
        调度配置，默认限制 3-8 人班级。
    temperature : float
        LLM 软判断采样温度。
    event_queue : Any | None
        可选事件队列。#25 正式 AgentEvent schema 尚未确定，因此这里只推送
        DirectorAgent 私有 payload，后续由事件适配层替换。
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        config: DirectorConfig | None = None,
        temperature: float = 0.4,
        event_queue: Any | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or DirectorConfig()
        self.temperature = temperature
        self.event_queue = event_queue
        self._template = _jinja_env.get_template("director.j2")
        self._rng = random.Random(self.config.seed)

    # -------------------------------------------------------------- public

    async def decide(
        self,
        teacher_utterance: str,
        stage: StageProfile,
        students: list[Persona],
        history: list[Message],
        elapsed_seconds: int,
    ) -> DirectorDecision:
        """根据当前课堂状态返回下一步调度决策。"""
        self._validate_students(students)

        by_id, aliases = self._student_maps(students)
        called = self._called_student(teacher_utterance, students)
        base = self._rule_decision(stage, students, history, elapsed_seconds, called)

        # 点名是硬约束，不能被 LLM 覆盖。
        if called is not None:
            decision = base
        else:
            llm_decision = await self._llm_decision(
                teacher_utterance,
                stage,
                students,
                history,
                elapsed_seconds,
            )
            decision = self._merge_and_sanitize(
                llm_decision,
                base,
                by_id,
                aliases,
                history,
                elapsed_seconds,
            )

        await self._emit(decision, elapsed_seconds)
        return decision

    # ------------------------------------------------------------- private

    def _validate_students(self, students: list[Persona]) -> None:
        if not (self.config.min_students <= len(students) <= self.config.max_students):
            raise ValueError(
                "students count must be between "
                f"{self.config.min_students} and {self.config.max_students}"
            )

    @staticmethod
    def _sid(student: Persona) -> str:
        return student.id or student.name

    def _student_maps(
        self,
        students: list[Persona],
    ) -> tuple[dict[str, Persona], dict[str, str]]:
        """返回规范 id 映射与姓名/id 别名映射。"""
        by_id: dict[str, Persona] = {}
        aliases: dict[str, str] = {}
        for student in students:
            sid = self._sid(student)
            by_id[sid] = student
            aliases[sid] = sid
            if student.name:
                aliases[student.name] = sid
            if student.id:
                aliases[student.id] = sid
        return by_id, aliases

    def _called_student(self, utterance: str, students: list[Persona]) -> Persona | None:
        """识别老师是否点名某学生。

        只匹配常见点名句式，避免把“小红花”“不是小红”误判为点名。
        """
        for student in students:
            if student.id and student.id in utterance:
                return student

            name = student.name
            if not name:
                continue
            if f"不是{name}" in utterance or f"不要{name}" in utterance:
                continue

            escaped = re.escape(name)
            patterns = [
                rf"(?:请|让|叫){escaped}",
                rf"{escaped}[，,、\s]*(?:你|来|回答|说说|试试)",
                rf"{escaped}.{{0,6}}(?:来回答|来说|试试|讲一下)",
            ]
            if any(re.search(pattern, utterance) for pattern in patterns):
                return student
        return None

    def _history_stats(
        self,
        history: list[Message],
        aliases: dict[str, str],
    ) -> tuple[dict[str, int], dict[str, int]]:
        """统计每个学生最近发言时间与历史发言次数。"""
        last: dict[str, int] = {}
        counts: dict[str, int] = {}
        for message in history:
            if message.role != "student" or not message.speaker_id:
                continue
            sid = aliases.get(message.speaker_id, message.speaker_id)
            counts[sid] = counts.get(sid, 0) + 1
            if message.timestamp_seconds is not None:
                last[sid] = message.timestamp_seconds
        return last, counts

    def _stage_traits(self, stage: StageProfile) -> tuple[int, int, float]:
        """由学段注意力特征推导动作间隔与走神基线。"""
        attention = stage.attention_features or ""
        minute_numbers = [int(value) for value in re.findall(r"\d+", attention)]
        focus_minutes = max(minute_numbers) if minute_numbers else None

        if focus_minutes is None:
            if stage.id == "h":
                focus_minutes = 45
            elif stage.id.startswith("p_lower"):
                focus_minutes = 20
            elif stage.id.startswith("p_"):
                focus_minutes = 25
            else:
                focus_minutes = 35

        if focus_minutes <= 20:
            lo, hi, daydream_base = 800, 2200, 0.34
        elif focus_minutes <= 25:
            lo, hi, daydream_base = 1200, 3200, 0.22
        elif focus_minutes < 45:
            lo, hi, daydream_base = 1800, 4500, 0.14
        else:
            lo, hi, daydream_base = 2800, 6000, 0.06

        if self.config.activity_level == "high":
            lo, hi = int(lo * 0.75), int(hi * 0.75)
            daydream_base *= 0.8
        elif self.config.activity_level == "low":
            lo, hi = int(lo * 1.25), int(hi * 1.25)
            daydream_base *= 1.15

        if self.config.discipline_level == "loose":
            daydream_base += 0.12
        else:
            daydream_base -= 0.04

        return lo, hi, max(0.0, min(daydream_base, 0.7))

    def _stage_delay(self, stage: StageProfile) -> int:
        lo, hi, _ = self._stage_traits(stage)
        delay = self._rng.randint(lo, hi)
        return max(self.config.min_delay_ms, min(delay, self.config.max_delay_ms))

    def _rule_decision(
        self,
        stage: StageProfile,
        students: list[Persona],
        history: list[Message],
        elapsed_seconds: int,
        called: Persona | None,
    ) -> DirectorDecision:
        delay = self._stage_delay(stage)
        by_id, aliases = self._student_maps(students)

        if called is not None:
            return DirectorDecision(
                actions=[
                    StudentAction(
                        speaker_id=self._sid(called),
                        action_type="speak",
                        priority=5,
                    )
                ],
                next_action_delay_ms=delay,
                rationale=f"老师点名 {called.name}，强制由该学生发言。",
            )

        last, counts = self._history_stats(history, aliases)
        available = [
            student
            for student in students
            if elapsed_seconds - last.get(self._sid(student), -9999)
            >= self.config.speaker_cooldown_seconds
        ]
        if not available:
            available = students

        # 发言配额：若仍有低于软配额的学生，优先在这些学生中轮换。
        under_quota = [
            student
            for student in available
            if counts.get(self._sid(student), 0) < self.config.max_speaks_per_student
        ]
        candidates = under_quota or available
        min_count = min(counts.get(self._sid(student), 0) for student in candidates)
        least_spoken = [
            student
            for student in candidates
            if counts.get(self._sid(student), 0) == min_count
        ]

        def score(student: Persona) -> float:
            freq = {"high": 2.0, "medium": 1.0, "low": 0.2}.get(
                student.interaction_frequency,
                1.0,
            )
            return freq + self._rng.random() * 0.25

        chosen = max(least_spoken, key=score)
        action, priority = self._rule_action(stage, chosen)
        if chosen.id not in by_id and chosen.name not in aliases:  # pragma: no cover
            raise RuntimeError("DirectorAgent internal student mapping error")

        return DirectorDecision(
            actions=[
                StudentAction(
                    speaker_id=self._sid(chosen),
                    action_type=action,
                    priority=priority,
                )
            ],
            next_action_delay_ms=delay,
            rationale=(
                "规则层依据冷却、发言配额、stage.attention_features 学段节奏"
                "与 persona.interaction_frequency 选择。"
            ),
        )

    def _rule_action(self, stage: StageProfile, student: Persona) -> tuple[str, int]:
        """根据学段、活跃度、纪律性和人设决定规则层动作。"""
        _, _, daydream_probability = self._stage_traits(stage)
        if student.attention_span == "short":
            daydream_probability += 0.12
        elif student.attention_span == "long":
            daydream_probability -= 0.08

        if self._rng.random() < max(0.0, min(daydream_probability, 0.8)):
            return "daydream", 2

        if student.interaction_frequency == "high":
            return "raise_hand", 4
        if student.interaction_frequency == "low" and self.config.activity_level == "low":
            return "silent", 1
        return "raise_hand", 3

    async def _llm_decision(
        self,
        teacher_utterance: str,
        stage: StageProfile,
        students: list[Persona],
        history: list[Message],
        elapsed_seconds: int,
    ) -> DirectorDecision | None:
        prompt = self._template.render(
            teacher_utterance=teacher_utterance,
            stage=stage,
            students=students,
            history=history,
            elapsed_seconds=elapsed_seconds,
            config=self.config,
        )
        try:
            resp = await self.llm.chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": teacher_utterance},
                ],
                temperature=self.temperature,
            )
            raw = resp.choices[0].message.content or ""
            return self._parse(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DirectorAgent LLM fallback: %s", exc)
            return None

    @staticmethod
    def _parse(raw: str) -> DirectorDecision | None:
        """从 LLM 原始输出中提取 JSON 并解析。"""
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return None
            json_str = match.group(0)

        try:
            return DirectorDecision(**json.loads(json_str))
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None

    def _merge_and_sanitize(
        self,
        llm_decision: DirectorDecision | None,
        base: DirectorDecision,
        by_id: dict[str, Persona],
        aliases: dict[str, str],
        history: list[Message],
        elapsed_seconds: int,
    ) -> DirectorDecision:
        """合并 LLM 软判断，并重新应用规则层硬约束。"""
        if llm_decision is None:
            return base

        last, counts = self._history_stats(history, aliases)
        fair_sids = self._fair_candidate_ids(
            list(by_id.values()),
            aliases,
            history,
            elapsed_seconds,
        )
        normalized: list[StudentAction] = []
        for action in llm_decision.actions:
            sid = aliases.get(action.speaker_id)
            if sid is None or sid not in by_id:
                continue

            action_type = action.action_type
            if action_type in {"speak", "raise_hand"}:
                in_cooldown = (
                    elapsed_seconds - last.get(sid, -9999)
                    < self.config.speaker_cooldown_seconds
                )
                quota_full = counts.get(sid, 0) >= self.config.max_speaks_per_student
                has_under_quota_peer = any(
                    counts.get(peer_sid, 0) < self.config.max_speaks_per_student
                    for peer_sid in by_id
                    if peer_sid != sid
                )
                if sid not in fair_sids or in_cooldown or (quota_full and has_under_quota_peer):
                    continue

            normalized.append(
                StudentAction(
                    speaker_id=sid,
                    action_type=action_type,
                    priority=action.priority,
                )
            )

        if not normalized:
            return base

        normalized = self._keep_single_speaker(normalized)
        normalized = sorted(normalized, key=lambda item: item.priority, reverse=True)[
            : self.config.max_actions_per_turn
        ]
        delay = self._bounded_llm_delay(llm_decision.next_action_delay_ms, base)

        return DirectorDecision(
            actions=normalized,
            next_action_delay_ms=delay,
            rationale=llm_decision.rationale or base.rationale,
        )

    def _fair_candidate_ids(
        self,
        students: list[Persona],
        aliases: dict[str, str],
        history: list[Message],
        elapsed_seconds: int,
    ) -> set[str]:
        """返回当前允许触发互动类动作的公平候选学生。"""
        last, counts = self._history_stats(history, aliases)
        available = [
            student
            for student in students
            if elapsed_seconds - last.get(self._sid(student), -9999)
            >= self.config.speaker_cooldown_seconds
        ]
        if not available:
            available = students

        under_quota = [
            student
            for student in available
            if counts.get(self._sid(student), 0) < self.config.max_speaks_per_student
        ]
        candidates = under_quota or available
        min_count = min(counts.get(self._sid(student), 0) for student in candidates)
        return {
            self._sid(student)
            for student in candidates
            if counts.get(self._sid(student), 0) == min_count
        }

    @staticmethod
    def _keep_single_speaker(actions: list[StudentAction]) -> list[StudentAction]:
        """同一轮最多允许一个 speak，其余 speak 降级为 raise_hand。"""
        speak_actions = [action for action in actions if action.action_type == "speak"]
        if len(speak_actions) <= 1:
            return actions

        keep = max(speak_actions, key=lambda item: item.priority)
        sanitized: list[StudentAction] = []
        for action in actions:
            if action.action_type != "speak" or action is keep:
                sanitized.append(action)
            else:
                sanitized.append(
                    StudentAction(
                        speaker_id=action.speaker_id,
                        action_type="raise_hand",
                        priority=min(action.priority, 4),
                    )
                )
        return sanitized

    def _bounded_llm_delay(
        self,
        llm_delay_ms: int,
        base: DirectorDecision,
    ) -> int:
        """LLM 只能在规则层学段节奏附近小幅调整 delay。"""
        base_delay = base.next_action_delay_ms
        lower = int(base_delay * 0.7)
        upper = int(base_delay * 1.3)
        delay = max(lower, min(llm_delay_ms, upper))
        return max(self.config.min_delay_ms, min(delay, self.config.max_delay_ms))

    async def _emit(self, decision: DirectorDecision, elapsed_seconds: int) -> None:
        if not self.event_queue:
            return

        # 临时内部 payload；正式 AgentEvent schema 待 #25 对齐后替换。
        payload = {
            "type": "director_decision",
            "decision": decision.model_dump(),
            "elapsed_seconds": elapsed_seconds,
        }
        if hasattr(self.event_queue, "put_nowait"):
            self.event_queue.put_nowait(payload)
            return
        if hasattr(self.event_queue, "put"):
            result = self.event_queue.put(payload)
            if inspect.isawaitable(result):
                await result
