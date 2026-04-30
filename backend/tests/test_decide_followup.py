"""StudentAgent.decide_followup 单元测试 (#A2 / #111)。

覆盖：

- 正常路径：should_followup=true + new_question 解析为完整 StudentQuestion
- 不追问路径：should_followup=false → new_question=None，reason 保留
- 文本重复降级：新问题 content 与已问过的一致 → no_followup
- JSON 格式损坏 / 缺字段 / 解析失败 → 全部优雅降级为 no_followup
- LLM 上游异常 → 优雅降级为 no_followup（不抛出）
- prompt 渲染：包含 persona / lesson / dialog_history / 已问列表
- 温度参数：决策类调用使用更低温度
- ``` 包裹的 JSON 也能解析
- linked_key_point 不在教案重点时被置空
- valid_misconception_ids 强约束为空（追问场景）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.dialog import DialogMessage
from schemas.followup import FollowupDecision
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from schemas.student import Persona


# ============================================================ fixtures


def _persona() -> Persona:
    return Persona(
        id="p1",
        name="小明",
        stage_id="p_middle",
        personality="活泼好动",
        knowledge_level="中等水平",
        behavior_traits="偶尔走神，但会积极回答",
    )


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="认识几分之一",
        objectives=["理解分数的基本含义"],
        key_points=["理解几分之一的含义", "认识分子分母"],
        difficult_points=["分子与分母的关系"],
    )


def _question(qid: str = "q-1", content: str = "老师，几分之一的'几'是什么意思？") -> StudentQuestion:
    return StudentQuestion(
        id=qid,
        speaker_id="p1",
        speaker_name="小明",
        content=content,
        category="clarify_concept",
        difficulty="easy",
        linked_key_point="理解几分之一的含义",
        rationale="想搞清楚分母含义。",
    )


def _history() -> list[DialogMessage]:
    now = datetime.now(timezone.utc)
    return [
        DialogMessage(role="teacher", content="你说说看你怎么想的？", timestamp=now),
        DialogMessage(
            role="student",
            content="嗯……我觉得分母是下面那个数？",
            timestamp=now,
            self_resolved=False,
        ),
        DialogMessage(
            role="teacher",
            content="对的！分母代表把整体分成几等份。",
            timestamp=now,
        ),
        DialogMessage(
            role="student",
            content="哦！我懂一点点了。",
            timestamp=now,
            self_resolved=True,
        ),
    ]


def _make_mock_llm(text: str) -> LLMClient:
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock(return_value=resp)
    return client


def _make_agent(llm: LLMClient) -> StudentAgent:
    return StudentAgent(llm=llm, persona=_persona(), misconceptions=[])


# ============================================================ 正常路径


async def test_decide_followup_should_followup_true() -> None:
    """LLM 输出合法 should_followup=true 时返回完整新问题。"""
    payload = {
        "should_followup": True,
        "reason": "学生刚理解了分母，对分子产生了好奇",
        "new_question": {
            "content": "那分子又是什么意思呢？",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": "认识分子分母",
            "rationale": "学生对分子分母配对理解有兴趣",
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )

    assert isinstance(decision, FollowupDecision)
    assert decision.should_followup is True
    assert decision.new_question is not None
    assert decision.new_question.content == "那分子又是什么意思呢？"
    assert decision.new_question.category == "clarify_concept"
    assert decision.new_question.difficulty == "easy"
    assert decision.new_question.linked_key_point == "认识分子分母"
    # 自动补齐元数据
    assert decision.new_question.id  # 非空 UUID
    assert decision.new_question.speaker_id == "p1"
    assert decision.new_question.speaker_name == "小明"
    assert "分子" in decision.reason


async def test_decide_followup_should_followup_false() -> None:
    """LLM 决定不追问时返回 should_followup=False、new_question=None。"""
    payload = {
        "should_followup": False,
        "reason": "学生刚说懂了，给老师一些消化时间",
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )

    assert decision.should_followup is False
    assert decision.new_question is None
    assert "刚说懂" in decision.reason


async def test_decide_followup_accepts_markdown_wrapped_json() -> None:
    """LLM 用 ```json``` 包裹输出也应能解析。"""
    payload = {
        "should_followup": True,
        "reason": "好奇",
        "new_question": {
            "content": "分子可以是 0 吗？",
            "category": "challenge_example",
            "difficulty": "medium",
            "linked_key_point": "认识分子分母",
        },
    }
    raw = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    llm = _make_mock_llm(raw)
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )

    assert decision.should_followup is True
    assert decision.new_question is not None
    assert decision.new_question.content == "分子可以是 0 吗？"


# ============================================================ 重复检测


async def test_decide_followup_drops_duplicate_question() -> None:
    """新问题文本与已问过的某条一致 → 降级 no_followup。"""
    asked_q = _question(qid="q-1", content="什么是分母？")
    payload = {
        "should_followup": True,
        "reason": "想再问一遍",
        "new_question": {
            "content": "什么是分母？",  # 与 asked 中重复
            "category": "clarify_concept",
            "difficulty": "easy",
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=asked_q,
        dialog_history=_history(),
        lesson_meta=_lesson(),
        asked_questions=[asked_q],
    )

    assert decision.should_followup is False
    assert decision.new_question is None
    assert "duplicate" in decision.reason.lower()


async def test_decide_followup_duplicate_check_strips_whitespace() -> None:
    """重复检测应忽略首尾空白。"""
    asked_q = _question(qid="q-1", content="什么是分母？")
    payload = {
        "should_followup": True,
        "reason": "x",
        "new_question": {
            "content": "  什么是分母？  ",  # 仅空白差异
            "category": "clarify_concept",
            "difficulty": "easy",
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=asked_q,
        dialog_history=_history(),
        lesson_meta=_lesson(),
        asked_questions=[asked_q],
    )
    assert decision.should_followup is False


# ============================================================ 解析失败降级


async def test_decide_followup_no_json_object_returns_no_followup() -> None:
    """LLM 输出完全不含 JSON → 降级。"""
    llm = _make_mock_llm("我今天有点累，先不追问了。")
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is False
    assert decision.new_question is None
    assert "parse_error" in decision.reason


async def test_decide_followup_invalid_json_syntax_returns_no_followup() -> None:
    """JSON 语法错误 → 降级。"""
    llm = _make_mock_llm('{"should_followup": true, "new_question": {broken')
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is False
    assert "parse_error" in decision.reason


async def test_decide_followup_should_true_but_new_question_missing() -> None:
    """should_followup=true 但缺 new_question → 降级。"""
    payload = {"should_followup": True, "reason": "想问"}
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is False
    assert "new_question missing" in decision.reason


async def test_decide_followup_new_question_empty_content_falls_back() -> None:
    """new_question.content 为空 → _build_question 抛错 → 降级。"""
    payload = {
        "should_followup": True,
        "reason": "x",
        "new_question": {
            "content": "",
            "category": "clarify_concept",
            "difficulty": "easy",
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is False
    assert "parse_error" in decision.reason


# ============================================================ LLM 上游异常


async def test_decide_followup_llm_failure_returns_no_followup() -> None:
    """LLM .chat 抛异常 → 优雅降级，不向上抛出。"""
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock(side_effect=RuntimeError("boom"))
    agent = _make_agent(client)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is False
    assert "llm_error" in decision.reason
    assert "boom" in decision.reason


# ============================================================ prompt 校验


async def test_decide_followup_prompt_contains_context() -> None:
    """prompt system 段必须含 persona / 当前 question / lesson / 历史 / 已问列表。"""
    llm = _make_mock_llm('{"should_followup": false, "reason": "x"}')
    agent = _make_agent(llm)

    asked = [
        _question(qid="q-1", content="什么是分母？"),
        _question(qid="q-2", content="什么是分子？"),
    ]
    await agent.decide_followup(
        current_question=asked[-1],
        dialog_history=_history(),
        lesson_meta=_lesson(),
        asked_questions=asked,
    )

    call_kwargs = llm.chat.call_args  # type: ignore[attr-defined]
    messages = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs["messages"]
    system_prompt = messages[0]["content"]

    assert "小明" in system_prompt  # persona
    assert "认识几分之一" in system_prompt  # lesson topic
    assert "什么是分子？" in system_prompt  # current question
    assert "什么是分母？" in system_prompt  # 已问列表
    assert "分母代表把整体分成几等份" in system_prompt  # 历史中的老师发言
    assert "should_followup" in system_prompt  # 输出格式说明


async def test_decide_followup_uses_lower_temperature() -> None:
    """决策类任务温度应低于 chat 的默认温度。"""
    llm = _make_mock_llm('{"should_followup": false, "reason": "x"}')
    agent = _make_agent(llm)
    # agent 默认 temperature=0.8
    assert agent.temperature == 0.8

    await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )

    call_kwargs = llm.chat.call_args  # type: ignore[attr-defined]
    used_temp = call_kwargs.kwargs.get("temperature")
    assert used_temp is not None
    assert used_temp <= 0.5
    # 同时不能低于 floor 0.3
    assert used_temp >= 0.3


# ============================================================ key_points 约束


async def test_decide_followup_clears_invalid_linked_key_point() -> None:
    """LLM 给出的 linked_key_point 不在教案 key_points 中 → 置空。"""
    payload = {
        "should_followup": True,
        "reason": "好奇",
        "new_question": {
            "content": "为什么 1+1=2？",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": "整数加法",  # 不在教案 key_points
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is True
    assert decision.new_question is not None
    assert decision.new_question.linked_key_point is None


async def test_decide_followup_strips_misconception_link() -> None:
    """追问场景下 linked_misconception_id 强制为空（即使 LLM 给了）。"""
    payload = {
        "should_followup": True,
        "reason": "x",
        "new_question": {
            "content": "新问题",
            "category": "stuck_misconception",
            "difficulty": "medium",
            "linked_misconception_id": "MC-0001",
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
    )
    assert decision.should_followup is True
    assert decision.new_question is not None
    # 即使 category=stuck_misconception，由于 valid_misconception_ids=set() 全部置空
    assert decision.new_question.linked_misconception_id is None


# ============================================================ default asked_questions


async def test_decide_followup_defaults_asked_to_current_only() -> None:
    """asked_questions=None 时，等价于仅含 current_question。"""
    payload = {
        "should_followup": True,
        "reason": "x",
        "new_question": {
            # 与 current_question 内容一致 → 应被重复过滤拦截
            "content": _question().content,
            "category": "clarify_concept",
            "difficulty": "easy",
        },
    }
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    decision = await agent.decide_followup(
        current_question=_question(),
        dialog_history=_history(),
        lesson_meta=_lesson(),
        # asked_questions 默认 None
    )
    assert decision.should_followup is False
    assert "duplicate" in decision.reason.lower()


# ============================================================ FollowupDecision 模型自身


def test_followup_decision_consistency_validator_blocks_inconsistent() -> None:
    """should_followup=True 但 new_question=None 应被 validator 拒绝。"""
    with pytest.raises(ValueError):
        FollowupDecision(should_followup=True, new_question=None, reason="x")


def test_followup_decision_consistency_validator_blocks_extra_question() -> None:
    """should_followup=False 但 new_question 非空也应被拒绝。"""
    with pytest.raises(ValueError):
        FollowupDecision(
            should_followup=False,
            new_question=_question(),
            reason="x",
        )


def test_followup_decision_no_followup_factory() -> None:
    """no_followup 工厂构造的对象字段一致。"""
    d = FollowupDecision.no_followup(reason="rate_limit")
    assert d.should_followup is False
    assert d.new_question is None
    assert d.reason == "rate_limit"
