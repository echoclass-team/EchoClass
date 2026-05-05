"""评估报告 schema — M3 协议冻结占位（Epic #121 / 真实实现 #M3-A1）。

与 ``docs/api_contract.md §2.6`` 保持一致。

本文件在 Epic 0（#121）阶段**仅定义字段契约**，供 B 端（#M3-B3 评估 REST API）
和前端（#M3-B4 复盘 UI）基于此 schema 搭骨架。真实 LLM 打分逻辑由 EvaluatorAgent
在 #M3-A3 填充；字段 / 约束若需变更，必须开 PR 修改本文件 + api_contract §2.6，
经 A+B 双 approve 后合入（与 ws_events.py / qa_session_api.py 同规则）。

不变式（与文档一致）：

- 每个 session 最多一份 ``EvaluationReport``（DB 层 ``evaluations.session_id UNIQUE``）
- LLM 失败时 ``overall="unavailable"``，``scores`` 可为空列表（字段不为 null）
- ``rubric_version`` 与 ``data/rubrics/{v}.json`` 绑定；历史 session 不追溯重算
- 前端反解析应对未知 ``dimension`` 静默忽略（向前兼容）
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """打分时引用的对话片段。"""

    dialog_id: str = Field(
        ...,
        description="对话线程 id（连续答疑模式下 == student_id）",
    )
    chunk_seq: int | None = Field(
        default=None,
        description="证据出现在该 dialog 第几轮 reply（可选）；未定位到具体轮次时为 None",
    )
    excerpt: str = Field(
        ...,
        max_length=120,
        description="原文摘录，≤ 120 字。避免泄露全文，仅保留定位所需片段。",
    )


class RubricScore(BaseModel):
    """单一维度的评估结果。"""

    dimension: str = Field(
        ...,
        description=(
            "Rubric 维度 id（与 ``data/rubrics/{rubric_version}.json`` 的维度 key 对应）。"
            "前端遇到未知 id 应静默忽略，不得报错。"
        ),
    )
    score: int = Field(
        ...,
        ge=0,
        le=4,
        description="0–4 整数分，语义参考 Rubric 维度定义",
    )
    rationale: str = Field(
        ...,
        max_length=200,
        description="打分理由（≤ 200 字）。应引用具体对话片段。",
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="支撑片段列表；可空，但强烈建议每个维度至少 1 条。",
    )


class EvaluationReport(BaseModel):
    """对一次 QASession 的完整 Rubric 评估。

    生成时机：``POST /api/qa-sessions/{id}/end`` 后异步触发；
    查询接口：``GET /api/qa-sessions/{id}/evaluation``（详见 api_contract §2.6）。
    """

    session_id: str = Field(..., description="评估所属 QASession id")
    rubric_version: str = Field(
        ...,
        description=(
            "使用的 Rubric 版本，如 ``v0`` / ``v1``。"
            "与 ``data/rubrics/{version}.json`` 一一对应。"
        ),
    )
    scores: list[RubricScore] = Field(
        default_factory=list,
        description="每个维度一条；LLM 部分失败时可能为子集或空列表",
    )
    overall: float | Literal["unavailable"] = Field(
        ...,
        description=(
            "汇总分（0.0–4.0 浮点，允许小数以表达维度加权平均）；"
            "LLM 整体失败时降级为字符串 ``\"unavailable\"``。"
        ),
    )
    generated_at: datetime = Field(
        ...,
        description="评估完成时间（UTC）",
    )


__all__ = ["Evidence", "RubricScore", "EvaluationReport"]
