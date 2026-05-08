"""StudentAgent.respond_in_dialog 单元测试。

覆盖：
- 正常回复返回 DialogReplyResult，content 为纯文本
- 末尾 [懂了] 标记被解析为 self_resolved=True 并从 content 剥离
- 标记前后空白容忍
- 没有标记时 self_resolved=False
- 空响应回退为 ……
- prompt 里包含 question / dialog_history / teacher_utterance 关键字段
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.dialog import DialogMessage
from schemas.question import StudentQuestion
from schemas.student import Persona


def _persona() -> Persona:
    return Persona(
        id="p1",
        name="小明",
        stage_id="p_middle",
        knowledge_level="中等水平",
        behavior_traits="偶尔走神，但会积极回答",
    )


def _question(category: str = "clarify_concept") -> StudentQuestion:
    return StudentQuestion(
        id="q-1",
        speaker_id="p1",
        speaker_name="小明",
        content="老师，几分之一的'几'是什么意思？",
        category=category,  # type: ignore[arg-type]
        difficulty="easy",
        linked_key_point="理解几分之一的含义",
        rationale="分子分母分不清。",
    )


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
    return StudentAgent(
        llm=llm,
        persona=_persona(),
        misconceptions=[],
    )


# ============================================================ tests


async def test_respond_in_dialog_returns_plain_text() -> None:
    llm = _make_mock_llm("哦，原来是这样啊！我明白一点了。")
    agent = _make_agent(llm)

    result = await agent.respond_in_dialog(
        question=_question(),
        teacher_utterance="几分之一的'几'就是分母，表示一共分成几份。",
    )

    assert result.content == "哦，原来是这样啊！我明白一点了。"
    assert result.self_resolved is False


async def test_respond_in_dialog_detects_resolve_marker() -> None:
    llm = _make_mock_llm("哦！我懂了，谢谢老师。\n[懂了]")
    agent = _make_agent(llm)

    result = await agent.respond_in_dialog(
        question=_question(),
        teacher_utterance="所以分母代表分成几份，分子代表取几份。",
    )

    assert result.self_resolved is True
    assert "[懂了]" not in result.content
    assert result.content.endswith("谢谢老师。")
    assert "[懂了]" in result.raw  # raw 保留原始输出便于排错


async def test_respond_in_dialog_marker_with_whitespace_variants() -> None:
    """[ 懂了 ] / 末尾多换行 也应被识别。"""
    llm = _make_mock_llm("我会了！\n\n[ 懂了 ]   \n")
    agent = _make_agent(llm)

    result = await agent.respond_in_dialog(
        question=_question(),
        teacher_utterance="懂了吧？",
    )
    assert result.self_resolved is True
    assert result.content == "我会了！"


async def test_respond_in_dialog_marker_in_middle_not_triggered() -> None:
    """`[懂了]` 出现在中间而非末尾不应触发 self_resolved。"""
    llm = _make_mock_llm("我[懂了]一点点，但还有疑问，那 1/3 呢？")
    agent = _make_agent(llm)

    result = await agent.respond_in_dialog(
        question=_question(),
        teacher_utterance="...",
    )
    assert result.self_resolved is False
    assert "[懂了]" in result.content  # 不剥离非末尾出现的


async def test_respond_in_dialog_empty_response_falls_back() -> None:
    """LLM 返回空字符串时 content 回退为 ……。"""
    llm = _make_mock_llm("")
    agent = _make_agent(llm)

    result = await agent.respond_in_dialog(
        question=_question(),
        teacher_utterance="...",
    )
    assert result.content == "……"
    assert result.self_resolved is False


async def test_respond_in_dialog_prompt_contains_question_and_history() -> None:
    """prompt 必须含 question.content 和历史中的发言。"""
    llm = _make_mock_llm("好的。")
    agent = _make_agent(llm)
    history = [
        DialogMessage(
            role="teacher",
            content="你能再具体描述下你的困惑吗？",
            timestamp=datetime.now(timezone.utc),
        ),
        DialogMessage(
            role="student",
            content="嗯……分母好像就是下面那个数？",
            timestamp=datetime.now(timezone.utc),
        ),
    ]

    await agent.respond_in_dialog(
        question=_question(),
        teacher_utterance="你想得对！分母在下面，代表分成几份。",
        dialog_history=history,
    )

    system_msg = llm.chat.call_args[0][0][0]["content"]
    assert "几分之一的'几'是什么意思？" in system_msg  # question
    assert "你能再具体描述下你的困惑吗？" in system_msg  # 历史 teacher
    assert "嗯……分母好像就是下面那个数？" in system_msg  # 历史 student
    assert "你想得对！分母在下面" in system_msg  # 本轮 teacher


async def test_respond_in_dialog_prompt_warns_for_stuck_misconception() -> None:
    """category=stuck_misconception 时 prompt 应含"不要说懂"提示。"""
    llm = _make_mock_llm("哦……")
    agent = _make_agent(llm)

    await agent.respond_in_dialog(
        question=_question(category="stuck_misconception"),
        teacher_utterance="不对哦，分母大不代表分数大。",
    )

    system_msg = llm.chat.call_args[0][0][0]["content"]
    assert "错误前提" in system_msg
    assert "不要说懂" in system_msg
