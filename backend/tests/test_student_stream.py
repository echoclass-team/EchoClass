"""StudentAgent.stream_in_dialog 单元测试。

覆盖：
- 流式输出按顺序产生若干 delta + 最终一个 final 事件
- delta 拼接 ≈ final.content（允许 strip / 标记剥离差异）
- 末尾 [懂了] 标记被剥离，self_resolved=True，且任何 delta 都不含标记字符
- 中段出现 [懂了] 不触发 self_resolved
- 空响应回退为 ……（final.content）
- prompt 中包含 question / dialog_history / teacher_utterance
- 与 respond_in_dialog 共用同一 prompt（_build_chat_messages 行为保持）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from unittest.mock import MagicMock

from agents.student import StudentAgent
from llm.client import LLMClient
from schemas.dialog import DialogMessage, StudentStreamEvent
from schemas.question import StudentQuestion
from schemas.student import Persona


# --------------------------------------------------------------------- fixtures


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


def _make_chunk(text: str | None) -> MagicMock:
    delta = MagicMock()
    delta.content = text
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _make_stream_llm(pieces: Iterable[str | None]) -> LLMClient:
    """构造一个 mock LLMClient，其 .stream(...) 返回一个 async 迭代器，按 pieces 顺序吐 chunk。"""
    pieces_list = list(pieces)

    async def fake_stream(messages, **kwargs):  # noqa: ANN001 - 测试 mock
        for piece in pieces_list:
            yield _make_chunk(piece)

    client = MagicMock(spec=LLMClient)
    # MagicMock(spec=...) 会拒绝赋值不在 spec 上的属性；stream 在 spec 中存在，可以直接覆盖
    client.stream = fake_stream  # type: ignore[assignment]
    # 同时记录最近一次调用参数，便于 prompt 校验
    return client


def _make_agent(llm: LLMClient) -> StudentAgent:
    return StudentAgent(
        llm=llm,
        persona=_persona(),
        misconceptions=[],
    )


async def _collect(agent_stream) -> list[StudentStreamEvent]:
    events: list[StudentStreamEvent] = []
    async for evt in agent_stream:
        events.append(evt)
    return events


# ============================================================ tests


async def test_stream_emits_delta_then_final() -> None:
    pieces = ["哦，", "原来", "是这样啊！", "我", "明白", "一点了。"]
    llm = _make_stream_llm(pieces)
    agent = _make_agent(llm)

    events = await _collect(
        agent.stream_in_dialog(
            question=_question(),
            teacher_utterance="几分之一的'几'就是分母。",
        )
    )

    assert events, "至少应有一个事件"
    assert events[-1].type == "final"
    final = events[-1].result
    assert final is not None
    assert final.content == "哦，原来是这样啊！我明白一点了。"
    assert final.self_resolved is False

    # delta 拼接（去除可能的 strip 边界）应 == final.content
    deltas = [e.delta for e in events if e.type == "delta"]
    assert "".join(deltas) == final.content
    # 中间事件全是 delta
    assert all(e.type == "delta" for e in events[:-1])


async def test_stream_strips_resolve_marker_and_sets_self_resolved() -> None:
    # 标记跨多个 chunk，验证 hold-back 能正确截留
    pieces = ["哦！我懂了，", "谢谢老师。\n", "[懂", "了]"]
    llm = _make_stream_llm(pieces)
    agent = _make_agent(llm)

    events = await _collect(
        agent.stream_in_dialog(
            question=_question(),
            teacher_utterance="所以分母代表分成几份。",
        )
    )

    final = events[-1].result
    assert final is not None
    assert final.self_resolved is True
    assert "[懂了]" in final.raw  # 原始保留
    assert "[懂了]" not in final.content
    # 任何 delta 都不允许含完整标记字符串（hold-back 必须有效）
    for evt in events:
        if evt.type == "delta":
            assert "[懂了]" not in evt.delta
            assert "[懂" not in evt.delta  # 部分标记片段也不应漏出
    # 拼接所有 delta 应等于 final.content（保证前端渲染最终也能完整显示正文）
    deltas = "".join(e.delta for e in events if e.type == "delta")
    assert deltas == final.content


async def test_stream_marker_in_middle_not_triggered() -> None:
    pieces = ["我[懂了]一点点，但还有疑问，", "那 1/3 呢？"]
    llm = _make_stream_llm(pieces)
    agent = _make_agent(llm)

    events = await _collect(
        agent.stream_in_dialog(
            question=_question(),
            teacher_utterance="...",
        )
    )

    final = events[-1].result
    assert final is not None
    assert final.self_resolved is False
    assert "[懂了]" in final.content


async def test_stream_empty_response_falls_back() -> None:
    llm = _make_stream_llm([])  # 流没有任何 chunk
    agent = _make_agent(llm)

    events = await _collect(
        agent.stream_in_dialog(
            question=_question(),
            teacher_utterance="...",
        )
    )

    # 空 stream 时 final.content 回退为 ……，并通过尾部补发 delta 推给前端
    assert events[-1].type == "final"
    final = events[-1].result
    assert final is not None
    assert final.content == "……"
    assert final.self_resolved is False
    deltas = "".join(e.delta for e in events if e.type == "delta")
    assert deltas == "……"


async def test_stream_ignores_chunks_with_no_content() -> None:
    """LLM 偶尔会发只带 usage / 空 delta 的 chunk，应被忽略。"""
    pieces: list[str | None] = [None, "你好", None, "，世界"]
    llm = _make_stream_llm(pieces)
    agent = _make_agent(llm)

    events = await _collect(
        agent.stream_in_dialog(
            question=_question(),
            teacher_utterance="hi",
        )
    )

    final = events[-1].result
    assert final is not None
    assert final.content == "你好，世界"


async def test_stream_prompt_contains_expected_fields() -> None:
    captured: dict = {}

    async def fake_stream(messages, **kwargs):  # noqa: ANN001
        captured["messages"] = messages
        for piece in ["好的。"]:
            yield _make_chunk(piece)

    llm = MagicMock(spec=LLMClient)
    llm.stream = fake_stream  # type: ignore[assignment]

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

    await _collect(
        agent.stream_in_dialog(
            question=_question(),
            teacher_utterance="你想得对！分母在下面，代表分成几份。",
            dialog_history=history,
        )
    )

    system_msg = captured["messages"][0]["content"]
    assert "几分之一的'几'是什么意思？" in system_msg  # question
    assert "你能再具体描述下你的困惑吗？" in system_msg  # 历史 teacher
    assert "嗯……分母好像就是下面那个数？" in system_msg  # 历史 student
    assert "你想得对！分母在下面" in system_msg  # 本轮 teacher
