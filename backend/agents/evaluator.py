"""EvaluatorAgent — 给一次 ``QASession`` 出 Rubric 评估报告（W2 / #M3-A1 骨架）。

设计原则
--------
- **本 issue 只交付骨架 + mock**，让 B3（评估 REST API）/ B4（复盘 UI）能并行
  消费。真实 LLM 打分逻辑由 #M3-A3 在本骨架基础上替换 ``_real_evaluate``。
- 接口契约由 ``schemas/evaluation.py`` 冻结（Epic #121 / PR #141），任何字段
  扩展必须先改 schema 文件 + ``docs/api_contract.md §2.6``，A+B 双 approve
  后合入。
- Rubric 内容由 C 在 #122 维护，存于 ``data/rubrics/{version}.json``；本 agent
  只读取，不构造维度。

使用
----
::

    from agents.evaluator import EvaluatorAgent

    # mock 模式（默认）：不调 LLM，每维度返 3 分占位
    evaluator = EvaluatorAgent()
    report = await evaluator.evaluate(session)

    # 真实模式：传入 LLMClient 实例（#M3-A3 落地后才支持）
    # evaluator = EvaluatorAgent(llm=LLMClient())
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm.client import LLMClient
from schemas.evaluation import EvaluationReport, RubricScore
from services.qa_session import QASession

logger = logging.getLogger(__name__)

RUBRIC_DIR: Path = (
    Path(__file__).resolve().parent.parent.parent / "data" / "rubrics"
)

# Mock 占位分（每维度统一 3 分，便于下游 UI 构图但明显是占位值）
_MOCK_SCORE = 3


def _project_message(message: Any, message_idx: int) -> dict[str, Any]:
    return {
        "message_idx": message_idx,
        "role": message.role,
        "content": message.content,
        "self_resolved": message.self_resolved,
        "is_new_question": message.is_new_question,
        "question_id": message.question_id,
    }


def build_dialog_projection(session: QASession) -> list[dict[str, Any]]:
    projections: list[dict[str, Any]] = []
    for dialog in session.dialogs.values():
        flat_messages = [
            _project_message(message, idx)
            for idx, message in enumerate(dialog.messages)
        ]
        questions: list[dict[str, Any]] = []
        if dialog.asked_questions and dialog.question_progress:
            for idx, question in enumerate(dialog.asked_questions):
                progress = (
                    dialog.question_progress[idx]
                    if idx < len(dialog.question_progress)
                    else None
                )
                start = progress.message_start_idx if progress is not None else 0
                end = (
                    progress.message_end_idx
                    if progress is not None and progress.message_end_idx is not None
                    else len(dialog.messages)
                )
                start = max(0, min(start, len(dialog.messages)))
                end = max(start, min(end, len(dialog.messages)))
                questions.append(
                    {
                        "question_index": idx,
                        "question_id": question.id,
                        "content": question.content,
                        "status": progress.status
                        if progress is not None
                        else dialog.status,
                        "turns_used": (
                            progress.turns_used
                            if progress is not None
                            else dialog.turn_count()
                        ),
                        "resolution_source": (
                            progress.resolution_source if progress is not None else None
                        ),
                        "messages": [
                            _project_message(message, msg_idx)
                            for msg_idx, message in enumerate(
                                dialog.messages[start:end], start=start
                            )
                        ],
                    }
                )
        else:
            questions.append(
                {
                    "question_index": 0,
                    "question_id": dialog.question.id,
                    "content": dialog.question.content,
                    "status": dialog.status,
                    "turns_used": dialog.turn_count(),
                    "resolution_source": dialog.resolution_source,
                    "messages": flat_messages,
                }
            )
        projections.append(
            {
                "dialog_id": dialog.id,
                "student_id": dialog.student_id,
                "persona_name": dialog.question.speaker_name,
                "status": dialog.status,
                "messages": flat_messages,
                "questions": questions,
            }
        )
    return projections


def load_rubric(version: str = "v0") -> dict[str, Any]:
    """加载 ``data/rubrics/{version}.json`` 并返回原始字典。

    返回字典的形状由 ``data/rubrics/_schema.json`` 约束（C 在 #122 维护）。
    本函数不做 schema 校验（已由 ``backend/scripts/validate_rubric.py`` 在
    CI 中独立保证），调用方按需读取 ``dimensions`` / ``scoring`` 等字段。
    """
    path = RUBRIC_DIR / f"{version}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Rubric not found: {path}. 可用版本见 data/rubrics/。"
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


class EvaluatorAgent:
    """对单次 QASession 产出 ``EvaluationReport``。

    Parameters
    ----------
    llm
        ``LLMClient`` 实例。**留 ``None`` 走 mock 模式**，本 issue（#M3-A1）
        只支持 mock；传入真实 client 会抛 ``NotImplementedError``，等 #M3-A3
        填入真实 prompt + 解析逻辑后再启用。
    rubric_version
        Rubric 版本号，对应 ``data/rubrics/{version}.json``。默认 ``v0``。
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        rubric_version: str = "v0",
    ) -> None:
        self.llm = llm
        self.rubric_version = rubric_version
        self.rubric = load_rubric(rubric_version)

    async def evaluate(self, session: QASession) -> EvaluationReport:
        """对 ``session`` 出一份 ``EvaluationReport``。

        当前实现：
        - ``llm is None`` → mock：每维度 ``score=3``、``evidence=[]``
        - 否则 → ``NotImplementedError``（等 #M3-A3）
        """
        if self.llm is None:
            return self._mock_evaluate(session)
        return await self._real_evaluate(session)

    # ------------------------------------------------------------------ mock

    def _mock_evaluate(self, session: QASession) -> EvaluationReport:
        """占位实现：每维度返回固定分。

        分数 ``_MOCK_SCORE = 3`` 是刻意取的中间值，让下游 UI 可视化能正常渲染
        但显然不应被当作真实评估。``rationale`` 文案明确标注 ``[mock]``。
        """
        dimensions = self.rubric.get("dimensions", [])
        scores = [
            RubricScore(
                dimension=dim["id"],
                score=_MOCK_SCORE,
                rationale=f"[mock] 维度 {dim.get('name_zh', dim['id'])} 的占位评分（真实评分见 #M3-A3）",
                evidence=[],
            )
            for dim in dimensions
        ]

        report = EvaluationReport(
            session_id=session.id,
            rubric_version=self.rubric_version,
            scores=scores,
            overall=float(_MOCK_SCORE),
            generated_at=datetime.now(timezone.utc),
        )
        logger.info(
            "EvaluatorAgent mock-evaluated session %s (%d dimensions, rubric=%s)",
            session.id,
            len(scores),
            self.rubric_version,
            extra={
                "event": "evaluator_mock",
                "session_id": session.id,
                "rubric_version": self.rubric_version,
                "dimensions": len(scores),
            },
        )
        return report

    # ------------------------------------------------------------------ real

    async def _real_evaluate(self, session: QASession) -> EvaluationReport:
        """真实 LLM 评估实现。**由 #M3-A3 填充。**

        预期流程（设计参考，非冻结）：

        1. 用 ``prompts/evaluator.j2`` 渲染 prompt：注入 rubric + 教案 +
           对话片段（``session.dialogs`` 摘要）
        2. ``self.llm.chat(...)`` 拿 JSON 输出
        3. 解析为 ``list[RubricScore]``，每条带 ≥1 条 ``Evidence``
        4. 失败时降级为 ``overall="unavailable"``，``scores`` 保留已成功的维度
           （契约见 ``docs/api_contract.md §2.6.4`` 不变式）
        """
        raise NotImplementedError(
            "Real LLM evaluation lands in #M3-A3. "
            "Pass llm=None to use the mock implementation."
        )


__all__ = ["EvaluatorAgent", "build_dialog_projection", "load_rubric"]
