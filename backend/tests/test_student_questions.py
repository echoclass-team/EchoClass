"""StudentAgent.generate_questions 单元测试（全程 mock LLM）。

覆盖：
- 正常路径：合法 JSON 数组解析为 list[StudentQuestion]，字段被正确填充
- count 限制：LLM 多产时裁剪到 count
- category / difficulty 非法值规范化为默认
- linked_key_point 不在教案重点列表里时置 None
- linked_misconception_id 不在迷思库 / category 不允许时置 None
- LLM 输出被 ```json``` 包裹仍能解析
- LLM 输出无效 JSON 时返回 []
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.lesson import LessonMeta
from schemas.misconception import Misconception
from schemas.student import Persona


# ============================================================ helpers


def _persona() -> Persona:
    return Persona(
        id="p_middle_weak_test",
        name="小红",
        stage_id="p_middle",
        knowledge_level="基础薄弱",
        behavior_traits="沉默寡言",
    )


def _lesson() -> LessonMeta:
    return LessonMeta(
        subject="数学",
        grade="三年级",
        topic="分数的初步认识",
        objectives=[],
        key_points=["理解几分之一的含义", "知道分数各部分名称"],
        difficult_points=["平均分是分数的基础"],
    )


def _misconception() -> Misconception:
    return Misconception(
        id="math_fraction_average_01",
        subject="数学",
        stage=["p_middle"],
        topic="分数的初步认识",
        name="不理解平均分",
        description="忽略平均分前提",
        typical_error="大小不一样也可以叫二分之一",
        cause="生活经验中的一半不要求严格等大",
    )


def _make_mock_llm(response_text: str) -> LLMClient:
    msg = MagicMock()
    msg.content = response_text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock(return_value=resp)
    return client


def _make_agent(
    llm: LLMClient, *, misconceptions: list[Misconception] | None = None
) -> StudentAgent:
    return StudentAgent(
        llm=llm,
        persona=_persona(),
        misconceptions=misconceptions
        if misconceptions is not None
        else [_misconception()],
    )


# ============================================================ tests


async def test_generate_questions_parses_valid_array() -> None:
    """三条合法问题被完整解析、字段被正确填充。"""
    payload: list[dict[str, Any]] = [
        {
            "content": "老师，几分之一的'几'是什么意思？",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": "理解几分之一的含义",
            "linked_misconception_id": None,
            "rationale": "我对分子分母的含义还分不清。",
        },
        {
            "content": "我觉得分一半就是二分之一，对吧？",
            "category": "stuck_misconception",
            "difficulty": "medium",
            "linked_key_point": "平均分是分数的基础",
            "linked_misconception_id": "math_fraction_average_01",
            "rationale": "生活经验里分一半不一定相等。",
        },
        {
            "content": "老师，下课能吃零食吗？",
            "category": "off_topic",
            "difficulty": "easy",
            "linked_key_point": None,
            "linked_misconception_id": None,
            "rationale": "我饿了。",
        },
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=3)

    assert len(questions) == 3
    assert {q.category for q in questions} == {
        "clarify_concept",
        "stuck_misconception",
        "off_topic",
    }
    assert all(q.id and q.speaker_id and q.speaker_name == "小红" for q in questions)
    stuck = [q for q in questions if q.category == "stuck_misconception"][0]
    assert stuck.linked_misconception_id == "math_fraction_average_01"
    assert stuck.linked_key_point == "平均分是分数的基础"


async def test_generate_questions_truncates_to_count() -> None:
    """LLM 多产时方法只保留 count 条。"""
    payload = [
        {
            "content": f"问题{i}",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": None,
            "linked_misconception_id": None,
            "rationale": "",
        }
        for i in range(5)
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=2)
    assert len(questions) == 2
    assert questions[0].content == "问题0"


async def test_generate_questions_normalizes_invalid_category() -> None:
    """非法 category 落到默认 clarify_concept。"""
    payload = [
        {
            "content": "随便问个什么",
            "category": "weird_unknown_category",
            "difficulty": "易",  # 中文也非法
            "linked_key_point": None,
            "linked_misconception_id": None,
            "rationale": "",
        }
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=1)
    assert questions[0].category == "clarify_concept"
    assert questions[0].difficulty == "medium"


async def test_generate_questions_clears_off_lesson_key_point() -> None:
    """LLM 编造的 key_point（不在教案中）应被置空，避免污染评估。"""
    payload = [
        {
            "content": "随便问问",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": "不存在的重点XYZ",
            "linked_misconception_id": None,
            "rationale": "",
        }
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=1)
    assert questions[0].linked_key_point is None


async def test_generate_questions_clears_misconception_when_category_disallows() -> (
    None
):
    """category=clarify_concept 不允许带迷思 id，即使 LLM 输出了也要置空。"""
    payload = [
        {
            "content": "啥意思啊",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": None,
            "linked_misconception_id": "math_fraction_average_01",
            "rationale": "",
        }
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=1)
    assert questions[0].linked_misconception_id is None


async def test_generate_questions_clears_unknown_misconception_id() -> None:
    """LLM 编造的 misconception_id（不在库里）应置空。"""
    payload = [
        {
            "content": "我觉得 1/4 大于 1/2，对吗？",
            "category": "stuck_misconception",
            "difficulty": "medium",
            "linked_key_point": None,
            "linked_misconception_id": "ghost_misconception_999",
            "rationale": "整数经验负迁移。",
        }
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=1)
    assert questions[0].linked_misconception_id is None
    assert questions[0].category == "stuck_misconception"


async def test_generate_questions_handles_code_fenced_json() -> None:
    """LLM 输出被 ```json``` 包裹仍能正确解析。"""
    inner = [
        {
            "content": "几分之一是不是分两半？",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": None,
            "linked_misconception_id": None,
            "rationale": "",
        }
    ]
    raw = "```json\n" + json.dumps(inner, ensure_ascii=False) + "\n```"
    llm = _make_mock_llm(raw)
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=1)
    assert len(questions) == 1
    assert questions[0].content == "几分之一是不是分两半？"


async def test_generate_questions_returns_empty_on_invalid_json() -> None:
    """LLM 完全没输出 JSON 数组时返回空列表，不抛异常。"""
    llm = _make_mock_llm("我今天有点累，不想想问题了……")
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=3)
    assert questions == []


async def test_generate_questions_skips_invalid_items() -> None:
    """数组里某个元素缺 content，应被跳过而不影响其他。"""
    payload = [
        {  # 缺 content，应被跳过
            "category": "clarify_concept",
            "difficulty": "easy",
        },
        {
            "content": "正常问题",
            "category": "clarify_concept",
            "difficulty": "easy",
            "linked_key_point": None,
            "linked_misconception_id": None,
            "rationale": "",
        },
    ]
    llm = _make_mock_llm(json.dumps(payload, ensure_ascii=False))
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=2)
    assert len(questions) == 1
    assert questions[0].content == "正常问题"


async def test_generate_questions_count_zero_returns_empty() -> None:
    """count<=0 时直接返回空列表，且不调用 LLM。"""
    llm = _make_mock_llm("[]")
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=0)
    assert questions == []
    llm.chat.assert_not_called()


# ====================================================== self-check 路径


def _make_mock_llm_seq(responses: list[str]) -> LLMClient:
    """按调用顺序返回不同响应文本的 mock LLM。

    第 N 次 ``chat`` 调用返回 ``responses[N]``；超出长度后重复最后一条。
    """
    seq = list(responses)

    async def fake_chat(*args, **kwargs):  # noqa: ANN001 - mock signature
        text = seq.pop(0) if len(seq) > 1 else seq[0]
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = None
        return resp

    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock(side_effect=fake_chat)
    return client


async def test_self_check_assigns_scores_and_filters_low() -> None:
    """self-check 应给每条候选写 self_score；keep=false 或 score<40 的被剔除。"""
    candidates_payload: list[dict[str, Any]] = [
        {
            "content": "高质量问题 A",
            "category": "clarify_concept",
            "difficulty": "easy",
        },
        {
            "content": "高质量问题 B",
            "category": "challenge_example",
            "difficulty": "medium",
        },
        {"content": "低质量问题 C", "category": "off_topic", "difficulty": "easy"},
    ]
    verdicts = [
        {"index": 0, "score": 88, "keep": True, "reason": "贴人设"},
        {"index": 1, "score": 82, "keep": True, "reason": "深思考"},
        {"index": 2, "score": 25, "keep": False, "reason": "完全跑偏"},
    ]
    llm = _make_mock_llm_seq(
        [
            json.dumps(candidates_payload, ensure_ascii=False),
            json.dumps(verdicts, ensure_ascii=False),
        ]
    )
    agent = _make_agent(llm)

    questions = await agent.generate_questions(
        _lesson(), count=3, overshoot=0, self_check=True
    )

    assert len(questions) == 2  # 第三条被 keep=false 剔除
    contents = {q.content for q in questions}
    assert "高质量问题 A" in contents
    assert "高质量问题 B" in contents
    assert "低质量问题 C" not in contents
    # self_score 都已写入
    assert all(q.self_score is not None for q in questions)


async def test_self_check_diverse_selection_prefers_unique_categories() -> None:
    """多样性筛选：相同 category 的候选只先取一个，给其他 category 留位置。"""
    candidates_payload: list[dict[str, Any]] = [
        {
            "content": "Q0 clarify-高分",
            "category": "clarify_concept",
            "difficulty": "easy",
        },
        {
            "content": "Q1 clarify-高分",
            "category": "clarify_concept",
            "difficulty": "easy",
        },
        {
            "content": "Q2 challenge-中分",
            "category": "challenge_example",
            "difficulty": "hard",
        },
    ]
    verdicts = [
        {"index": 0, "score": 95, "keep": True, "reason": ""},
        {"index": 1, "score": 92, "keep": True, "reason": ""},
        {"index": 2, "score": 70, "keep": True, "reason": ""},
    ]
    llm = _make_mock_llm_seq(
        [
            json.dumps(candidates_payload, ensure_ascii=False),
            json.dumps(verdicts, ensure_ascii=False),
        ]
    )
    agent = _make_agent(llm)

    # overshoot=1 让 target_count=3，3 条候选都进筛选阶段
    questions = await agent.generate_questions(
        _lesson(), count=2, overshoot=1, self_check=True
    )

    assert len(questions) == 2
    cats = [q.category for q in questions]
    assert cats == ["clarify_concept", "challenge_example"], (
        "类别多样性应优先于单一类别拿满"
    )


async def test_self_check_fallback_when_verdicts_invalid() -> None:
    """self-check 输出无效 JSON 时降级，仍返回 count 个候选（无 self_score）。"""
    candidates_payload: list[dict[str, Any]] = [
        {"content": "Q0", "category": "clarify_concept", "difficulty": "easy"},
        {"content": "Q1", "category": "challenge_example", "difficulty": "medium"},
    ]
    llm = _make_mock_llm_seq(
        [
            json.dumps(candidates_payload, ensure_ascii=False),
            "我无法评分",  # self-check 阶段输出无效 JSON
        ]
    )
    agent = _make_agent(llm)

    questions = await agent.generate_questions(
        _lesson(), count=2, overshoot=0, self_check=True
    )

    assert len(questions) == 2
    # self-check 失败降级，self_score 应未被写入
    assert all(q.self_score is None for q in questions)


async def test_self_check_disabled_skips_second_llm_call() -> None:
    """self_check=False 时方法只调一次 LLM。"""
    candidates_payload: list[dict[str, Any]] = [
        {"content": "Q0", "category": "clarify_concept", "difficulty": "easy"},
        {"content": "Q1", "category": "extend_topic", "difficulty": "medium"},
    ]
    llm = _make_mock_llm_seq([json.dumps(candidates_payload, ensure_ascii=False)])
    agent = _make_agent(llm)

    questions = await agent.generate_questions(_lesson(), count=2, self_check=False)

    assert len(questions) == 2
    assert llm.chat.await_count == 1


async def test_self_check_keeps_at_least_one_when_all_rejected() -> None:
    """self-check 把所有候选都标 keep=false 时，应至少保留 1 条最高分避免 0 候选。"""
    candidates_payload: list[dict[str, Any]] = [
        {"content": "Q0", "category": "clarify_concept", "difficulty": "easy"},
        {"content": "Q1", "category": "challenge_example", "difficulty": "medium"},
    ]
    verdicts = [
        {"index": 0, "score": 30, "keep": False, "reason": ""},
        {"index": 1, "score": 35, "keep": False, "reason": ""},
    ]
    llm = _make_mock_llm_seq(
        [
            json.dumps(candidates_payload, ensure_ascii=False),
            json.dumps(verdicts, ensure_ascii=False),
        ]
    )
    agent = _make_agent(llm)

    questions = await agent.generate_questions(
        _lesson(), count=2, overshoot=0, self_check=True
    )

    assert len(questions) == 1
    assert questions[0].content == "Q1"  # 35 > 30，最高分保留
