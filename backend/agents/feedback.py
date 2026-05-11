"""FeedbackAgent — 给师范生写结课反馈。

与 ``EvaluatorAgent`` 配对但**受众不同**：

- ``EvaluatorAgent`` → 评委 / 数据看板：维度打分 + 证据
- ``FeedbackAgent``（本文件）→ 师范生：自然语言的肯定 + 改进 + 下一步

设计原则：

- 默认 mock 模式不调 LLM；传入 ``LLMClient`` 时走真实 LLM 路径
- ``schemas/feedback.py`` 冻结接口，本 agent 只消费
- 与 ``EvaluatorAgent`` schema 解耦：``evaluation`` 仅作为可选输入参考，
  缺失时仍能给出占位反馈
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from agents.evaluator import build_dialog_projection
from llm.client import LLMClient
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from services.qa_session import QASession

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)

_VALID_TONES = {"encouraging", "neutral", "critical"}


def _extract_json_object(raw: str) -> dict[str, Any]:
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    candidate = match.group(1) if match else None
    if candidate is None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            candidate = raw[start : end + 1]
    if candidate is None:
        raise ValueError("no JSON object found in feedback output")
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("feedback output is not a JSON object")
    return data


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


class FeedbackAgent:
    """对一次 ``QASession`` 产出 ``TeacherFeedback``。

    Parameters
    ----------
    llm
        ``LLMClient`` 实例。留 ``None`` 走 mock 模式；传入真实 client 走
        prompt 渲染 + JSON 解析路径，失败时返回占位降级反馈。
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    async def generate(
        self,
        session: QASession,
        evaluation: EvaluationReport | None = None,
    ) -> TeacherFeedback:
        """对 ``session`` 出一份 ``TeacherFeedback``。

        Parameters
        ----------
        session
            待反馈的 QA session。
        evaluation
            EvaluatorAgent 同时刻产出的评估（若已生成）。可选——LLM 评估失败
            时仍允许直接出反馈（契约见 api_contract §2.6.4 降级语义）。

        当前实现：

        - ``llm is None`` → mock：返回固定的 ``[mock]`` 占位文案
        - 否则 → 调 LLM 生成反馈，失败时返回占位降级反馈
        """
        if self.llm is None:
            return self._mock_generate(session, evaluation)
        return await self._real_generate(session, evaluation)

    # ------------------------------------------------------------------ mock

    def _mock_generate(
        self,
        session: QASession,
        evaluation: EvaluationReport | None,
    ) -> TeacherFeedback:
        feedback = TeacherFeedback(
            strengths=[
                "[mock] 提问引导清晰，能让学生主动思考",
            ],
            improvements=[
                "[mock] 可在学生表达迷思时多用反例追问，避免直接给答案",
            ],
            next_steps=[
                "[mock] 下次答疑前梳理本课难点的常见误解，准备 2-3 个反例",
            ],
            tone="encouraging",
            generated_at=datetime.now(timezone.utc),
        )
        logger.info(
            "FeedbackAgent mock-generated for session %s (eval=%s)",
            session.id,
            "yes" if evaluation else "none",
            extra={
                "event": "feedback_mock",
                "session_id": session.id,
                "with_evaluation": evaluation is not None,
            },
        )
        return feedback

    # ------------------------------------------------------------------ real

    async def _real_generate(
        self,
        session: QASession,
        evaluation: EvaluationReport | None,
    ) -> TeacherFeedback:
        """真实 LLM 反馈：渲染 prompt → 调 LLM → 解析 JSON → 失败降级。

        短路：若 ``evaluation.overall == "unavailable"``（评估本身已降级），
        则跳过 LLM 直接返回占位反馈，避免在已知证据不足时继续烧 token。
        """
        if evaluation is not None and evaluation.overall == "unavailable":
            logger.info(
                "FeedbackAgent skipped LLM for %s: evaluation overall=unavailable",
                session.id,
            )
            return self._fallback_feedback()
        template = _jinja_env.get_template("feedback.j2")
        prompt = template.render(
            lesson=session.lesson_meta,
            dialogs=build_dialog_projection(session),
            evaluation=evaluation,
        )
        try:
            resp = await self.llm.chat(
                [{"role": "system", "content": prompt}],
                temperature=0.4,
            )
            raw = resp.choices[0].message.content or ""
            data = _extract_json_object(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FeedbackAgent real generation failed for session %s: %s",
                session.id,
                exc,
                exc_info=True,
            )
            return self._fallback_feedback()

        strengths = _coerce_str_list(data.get("strengths"))
        improvements = _coerce_str_list(data.get("improvements"))
        next_steps = _coerce_str_list(data.get("next_steps"))
        tone = data.get("tone")
        if tone not in _VALID_TONES:
            tone = "neutral"

        # 契约：三个列表均不得为空；缺失时补占位以保持 §2.6.4 降级语义
        if not strengths:
            strengths = ["[fallback] 本次反馈未能生成具体亮点，请结合对话自查。"]
        if not improvements:
            improvements = ["[fallback] 本次反馈未能生成具体改进点，请结合对话自查。"]
        if not next_steps:
            next_steps = ["[fallback] 建议回看对话并整理下次答疑的准备要点。"]

        return TeacherFeedback(
            strengths=strengths,
            improvements=improvements,
            next_steps=next_steps,
            tone=tone,
            generated_at=datetime.now(timezone.utc),
        )

    def _fallback_feedback(self) -> TeacherFeedback:
        return TeacherFeedback(
            strengths=["[fallback] 反馈生成暂不可用，请稍后重试。"],
            improvements=["[fallback] 反馈生成暂不可用，请稍后重试。"],
            next_steps=["[fallback] 反馈生成暂不可用，请稍后重试。"],
            tone="neutral",
            generated_at=datetime.now(timezone.utc),
        )


__all__ = ["FeedbackAgent"]
