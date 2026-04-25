"""StudentAgent snapshot tests — 3 personas × 3 utterances = 9 cases.

所有测试 mock LLMClient，验证：
1. prompt 正确包含人设 / 上下文 / 老师发言。
2. LLM 返回的 JSON 被正确解析为 StudentReply。
3. 各 intent / emotion 字段合法。
"""
from __future__ import annotations

import json
import random
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.misconception import Misconception
from schemas.student import ClassroomContext, Intent, Persona, StudentReply

# ============================================================ Fixtures


# --- 3 personas ---

WEAK_STUDENT = Persona(
    name="小红",
    personality="内向害羞",
    knowledge_level="基础薄弱",
    behavior_traits="沉默寡言，不敢举手",
)

MEDIUM_STUDENT = Persona(
    name="小明",
    personality="活泼好动",
    knowledge_level="中等水平",
    behavior_traits="偶尔走神，但会积极回答",
)

STRONG_STUDENT = Persona(
    name="小华",
    personality="认真严谨",
    knowledge_level="优等生",
    behavior_traits="积极举手，乐于帮助同学",
)

PERSONAS = [WEAK_STUDENT, MEDIUM_STUDENT, STRONG_STUDENT]

# --- 3 teacher utterances ---

UTTERANCES = [
    "同学们，什么是分数？谁能告诉我？",
    "1/2 + 1/3 等于多少？",
    "大家还有什么问题吗？",
]

# --- default classroom context ---

CONTEXT = ClassroomContext(
    subject="数学",
    topic="分数的概念与运算",
    history=[],
)

# --- 9 mock LLM replies (3 personas × 3 utterances) ---

MOCK_REPLIES: dict[tuple[str, str], dict[str, Any]] = {
    # --- 小红 (weak) ---
    ("小红", "同学们，什么是分数？谁能告诉我？"): {
        "speaker_id": "小红",
        "intent": "answer_question",
        "content": "分数就是……把数字上下摞在一起？",
        "emotion": "困惑",
    },
    ("小红", "1/2 + 1/3 等于多少？"): {
        "speaker_id": "小红",
        "intent": "answer_question",
        "content": "是不是 2/5 啊？把上面加上面，下面加下面……",
        "emotion": "紧张",
    },
    ("小红", "大家还有什么问题吗？"): {
        "speaker_id": "小红",
        "intent": "passive",
        "content": "……没有。",
        "emotion": "紧张",
    },
    # --- 小明 (medium) ---
    ("小明", "同学们，什么是分数？谁能告诉我？"): {
        "speaker_id": "小明",
        "intent": "answer_question",
        "content": "分数就是把一个东西分成几份，然后取其中几份！",
        "emotion": "兴奋",
    },
    ("小明", "1/2 + 1/3 等于多少？"): {
        "speaker_id": "小明",
        "intent": "answer_question",
        "content": "嗯……要通分吧，我算算，应该是 5/6？",
        "emotion": "自信",
    },
    ("小明", "大家还有什么问题吗？"): {
        "speaker_id": "小明",
        "intent": "off_topic",
        "content": "老师，今天中午吃什么？",
        "emotion": "无聊",
    },
    # --- 小华 (strong) ---
    ("小华", "同学们，什么是分数？谁能告诉我？"): {
        "speaker_id": "小华",
        "intent": "answer_question",
        "content": "分数是表示部分与整体关系的数，由分子和分母组成，分母不能为零。",
        "emotion": "自信",
    },
    ("小华", "1/2 + 1/3 等于多少？"): {
        "speaker_id": "小华",
        "intent": "answer_question",
        "content": "等于 5/6。先通分，最小公倍数是 6，所以 3/6 + 2/6 = 5/6。",
        "emotion": "自信",
    },
    ("小华", "大家还有什么问题吗？"): {
        "speaker_id": "小华",
        "intent": "ask_question",
        "content": "老师，分数和小数可以互相转换吗？怎么转？",
        "emotion": "兴奋",
    },
}


# ============================================================ Helpers


def _make_mock_llm(persona_name: str, utterance: str) -> LLMClient:
    """创建一个 mock LLMClient，chat() 返回预设的 JSON 回复。"""
    reply_data = MOCK_REPLIES[(persona_name, utterance)]
    reply_json = json.dumps(reply_data, ensure_ascii=False)

    mock_message = MagicMock()
    mock_message.content = reply_json

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = mock_usage

    mock_client = MagicMock(spec=LLMClient)
    mock_client.chat = AsyncMock(return_value=mock_resp)
    return mock_client


def _make_agent(mock_llm: LLMClient, persona: Persona) -> StudentAgent:
    """创建 StudentAgent，注入 mock LLM。"""
    ctx = CONTEXT.model_copy(deep=True)
    return StudentAgent(llm=mock_llm, persona=persona, context=ctx)


def _fraction_misconception() -> Misconception:
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


# ============================================================ Tests


VALID_INTENTS: set[Intent] = {"answer_question", "ask_question", "off_topic", "passive"}


@pytest.mark.parametrize(
    "persona",
    PERSONAS,
    ids=["weak_小红", "medium_小明", "strong_小华"],
)
@pytest.mark.parametrize(
    "utterance",
    UTTERANCES,
    ids=["什么是分数", "分数加法", "还有问题吗"],
)
async def test_student_reply_structure(persona: Persona, utterance: str) -> None:
    """验证每个 (persona, utterance) 组合返回合法 StudentReply。"""
    mock_llm = _make_mock_llm(persona.name, utterance)
    agent = _make_agent(mock_llm, persona)

    reply = await agent.respond(utterance)

    # 类型正确
    assert isinstance(reply, StudentReply)
    # speaker_id 匹配
    assert reply.speaker_id == persona.name
    # intent 合法
    assert reply.intent in VALID_INTENTS
    # content 非空
    assert len(reply.content) > 0
    # emotion 非空
    assert len(reply.emotion) > 0


@pytest.mark.parametrize(
    "persona",
    PERSONAS,
    ids=["weak_小红", "medium_小明", "strong_小华"],
)
@pytest.mark.parametrize(
    "utterance",
    UTTERANCES,
    ids=["什么是分数", "分数加法", "还有问题吗"],
)
async def test_student_reply_snapshot(persona: Persona, utterance: str) -> None:
    """Snapshot: 验证 mock 回复与预期完全一致。"""
    mock_llm = _make_mock_llm(persona.name, utterance)
    agent = _make_agent(mock_llm, persona)

    reply = await agent.respond(utterance)
    expected = MOCK_REPLIES[(persona.name, utterance)]

    assert reply.speaker_id == expected["speaker_id"]
    assert reply.intent == expected["intent"]
    assert reply.content == expected["content"]
    assert reply.emotion == expected["emotion"]


@pytest.mark.parametrize(
    "persona",
    PERSONAS,
    ids=["weak_小红", "medium_小明", "strong_小华"],
)
@pytest.mark.parametrize(
    "utterance",
    UTTERANCES,
    ids=["什么是分数", "分数加法", "还有问题吗"],
)
async def test_prompt_contains_persona_and_context(
    persona: Persona, utterance: str
) -> None:
    """验证 prompt 包含人设信息、课堂上下文和老师发言。"""
    mock_llm = _make_mock_llm(persona.name, utterance)
    agent = _make_agent(mock_llm, persona)

    await agent.respond(utterance)

    # 检查 chat 被调用
    mock_llm.chat.assert_called_once()
    call_args = mock_llm.chat.call_args
    messages = call_args[0][0]

    # system message 包含人设
    system_msg = messages[0]["content"]
    assert persona.name in system_msg
    assert persona.personality in system_msg
    assert persona.knowledge_level in system_msg
    assert persona.behavior_traits in system_msg

    # system message 包含课堂信息
    assert CONTEXT.subject in system_msg
    assert CONTEXT.topic in system_msg

    # user message 是老师发言
    assert messages[1]["content"] == utterance


async def test_prompt_contains_matched_misconception_details() -> None:
    """prompt 应包含匹配迷思的 id、typical_error、cause。"""
    mock_llm = _make_mock_llm("小红", "同学们，什么是分数？谁能告诉我？")
    ctx = ClassroomContext(
        subject="数学",
        topic="分数",
        key_points=["分数的初步认识"],
    )
    persona = WEAK_STUDENT.model_copy(update={"stage_id": "p_middle"})
    misconception = _fraction_misconception()
    agent = StudentAgent(
        llm=mock_llm,
        persona=persona,
        context=ctx,
        misconceptions=[misconception],
        rng=random.Random(999),
    )

    await agent.respond("同学们，什么是分数？谁能告诉我？")

    system_msg = mock_llm.chat.call_args[0][0][0]["content"]
    assert misconception.id in system_msg
    assert misconception.typical_error in system_msg
    assert misconception.cause in system_msg


async def test_weak_student_auto_fills_triggered_misconception_id() -> None:
    """薄弱学生触发迷思且 LLM 未返回 id 时，自动补充触发 id。"""
    mock_llm = _make_mock_llm("小红", "同学们，什么是分数？谁能告诉我？")
    ctx = ClassroomContext(subject="数学", topic="分数", key_points=["分数的初步认识"])
    persona = WEAK_STUDENT.model_copy(update={"stage_id": "p_middle"})
    misconception = _fraction_misconception()
    agent = StudentAgent(
        llm=mock_llm,
        persona=persona,
        context=ctx,
        misconceptions=[misconception],
        rng=random.Random(1),
    )

    reply = await agent.respond("同学们，什么是分数？谁能告诉我？")

    assert reply.triggered_misconception_id == misconception.id
    system_msg = mock_llm.chat.call_args[0][0][0]["content"]
    assert "本轮触发" in system_msg


async def test_strong_student_without_trigger_has_no_trigger_requirement() -> None:
    """优秀学生未触发时，prompt 不出现本轮触发要求且 reply id 为空。"""
    mock_llm = _make_mock_llm("小华", "同学们，什么是分数？谁能告诉我？")
    ctx = ClassroomContext(subject="数学", topic="分数", key_points=["分数的初步认识"])
    persona = STRONG_STUDENT.model_copy(update={"stage_id": "p_middle"})
    agent = StudentAgent(
        llm=mock_llm,
        persona=persona,
        context=ctx,
        misconceptions=[_fraction_misconception()],
        rng=random.Random(1),
    )

    reply = await agent.respond("同学们，什么是分数？谁能告诉我？")

    assert reply.triggered_misconception_id is None
    system_msg = mock_llm.chat.call_args[0][0][0]["content"]
    assert "⚠️ 本轮触发" not in system_msg


async def test_untriggered_llm_misconception_id_is_cleared() -> None:
    """RNG 未触发时，即使 LLM 自行填写候选 id，也应清空以保证概率可控。"""
    reply_json = json.dumps(
        {
            "speaker_id": "小华",
            "intent": "answer_question",
            "content": "分数是平均分的一部分。",
            "emotion": "自信",
            "triggered_misconception_id": "math_fraction_average_01",
        },
        ensure_ascii=False,
    )
    mock_message = MagicMock()
    mock_message.content = reply_json
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat = AsyncMock(return_value=mock_resp)
    ctx = ClassroomContext(subject="数学", topic="分数", key_points=["分数的初步认识"])
    persona = STRONG_STUDENT.model_copy(update={"stage_id": "p_middle"})
    agent = StudentAgent(
        llm=mock_llm,
        persona=persona,
        context=ctx,
        misconceptions=[_fraction_misconception()],
        rng=random.Random(1),
    )

    reply = await agent.respond("同学们，什么是分数？谁能告诉我？")

    assert reply.triggered_misconception_id is None


async def test_non_answer_reply_clears_triggered_misconception_id() -> None:
    """只有 answer_question 才记录触发的学科迷思。"""
    reply_json = json.dumps(
        {
            "speaker_id": "小红",
            "intent": "passive",
            "content": "嗯……",
            "emotion": "紧张",
            "triggered_misconception_id": "math_fraction_average_01",
        },
        ensure_ascii=False,
    )
    mock_message = MagicMock()
    mock_message.content = reply_json
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat = AsyncMock(return_value=mock_resp)
    ctx = ClassroomContext(subject="数学", topic="分数", key_points=["分数的初步认识"])
    persona = WEAK_STUDENT.model_copy(update={"stage_id": "p_middle"})
    agent = StudentAgent(
        llm=mock_llm,
        persona=persona,
        context=ctx,
        misconceptions=[_fraction_misconception()],
        rng=random.Random(1),
    )

    reply = await agent.respond("同学们，什么是分数？谁能告诉我？")

    assert reply.triggered_misconception_id is None


# --- 边缘情况 ---


async def test_parse_json_in_code_block() -> None:
    """LLM 输出被 ```json ... ``` 包裹时仍能正确解析。"""
    reply_json = json.dumps(
        {
            "speaker_id": "小红",
            "intent": "passive",
            "content": "嗯……",
            "emotion": "紧张",
        },
        ensure_ascii=False,
    )
    raw = f"好的，以下是回复：\n```json\n{reply_json}\n```"

    mock_message = MagicMock()
    mock_message.content = raw
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat = AsyncMock(return_value=mock_resp)

    agent = _make_agent(mock_llm, WEAK_STUDENT)
    reply = await agent.respond("什么是分数？")

    assert reply.speaker_id == "小红"
    assert reply.intent == "passive"


async def test_parse_fallback_on_invalid_json() -> None:
    """LLM 输出无效 JSON 时应 fallback 为 passive。"""
    mock_message = MagicMock()
    mock_message.content = "我不知道该怎么回答"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.chat = AsyncMock(return_value=mock_resp)

    agent = _make_agent(mock_llm, WEAK_STUDENT)
    reply = await agent.respond("什么是分数？")

    assert reply.speaker_id == "小红"
    assert reply.intent == "passive"
    assert reply.emotion == "困惑"


async def test_context_history_updated() -> None:
    """调用 respond 后课堂历史应被更新。"""
    mock_llm = _make_mock_llm("小明", "同学们，什么是分数？谁能告诉我？")
    agent = _make_agent(mock_llm, MEDIUM_STUDENT)

    assert len(agent.context.history) == 0
    await agent.respond("同学们，什么是分数？谁能告诉我？")
    assert len(agent.context.history) == 2
    assert "老师：" in agent.context.history[0]
    assert "小明" in agent.context.history[1]
