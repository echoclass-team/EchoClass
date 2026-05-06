"""FeedbackAgent — 给师范生写结课反馈（W2 / #M3-A2 骨架）。

与 ``EvaluatorAgent`` 配对但**受众不同**：

- ``EvaluatorAgent``（#M3-A1）→ 评委 / 数据看板：维度打分 + 证据
- ``FeedbackAgent``（本文件）→ 师范生：自然语言的肯定 + 改进 + 下一步

设计原则与 #M3-A1 对齐：

- 骨架 + mock 优先；真实 LLM 实现由 #M3-A4 在 ``_real_generate`` 里替换
- ``schemas/feedback.py`` 已在 Epic #121 / PR #141 冻结，本 agent 只消费
- 与 ``EvaluatorAgent`` schema 解耦：``evaluation`` 仅作为可选输入参考（缺失
  时仍能给出占位反馈，配合 ``docs/api_contract.md §2.6.4`` 的降级语义）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from llm.client import LLMClient
from schemas.evaluation import EvaluationReport
from schemas.feedback import TeacherFeedback
from services.qa_session import QASession

logger = logging.getLogger(__name__)


class FeedbackAgent:
    """对一次 ``QASession`` 产出 ``TeacherFeedback``。

    Parameters
    ----------
    llm
        ``LLMClient`` 实例。**留 ``None`` 走 mock 模式**，本 issue（#M3-A2）
        只支持 mock；传入真实 client 抛 ``NotImplementedError``，等 #M3-A4
        替换。
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
        - 否则 → ``NotImplementedError``（等 #M3-A4）
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
        """真实 LLM 反馈实现。**由 #M3-A4 填充。**

        预期流程（设计参考，非冻结）：

        1. 用 ``prompts/feedback.j2`` 渲染：注入对话片段 + 评估分（若有）
        2. ``self.llm.chat(...)`` 获取 JSON 输出
        3. 解析为 ``TeacherFeedback``，``tone`` 字段必须是 schema 三选一
        4. LLM 失败时降级：strengths/improvements/next_steps 用占位文案，
           ``tone="neutral"``，字段不为 null（契约 api_contract §2.6.4）
        """
        raise NotImplementedError(
            "Real LLM feedback lands in #M3-A4. "
            "Pass llm=None to use the mock implementation."
        )


__all__ = ["FeedbackAgent"]
