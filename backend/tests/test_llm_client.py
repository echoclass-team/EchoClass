"""Unit tests for LLMClient.

全程 mock `AsyncOpenAI`，不发真实网络请求。
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APITimeoutError, AsyncOpenAI, AuthenticationError, RateLimitError

from llm.client import LLMClient


# ------------------------------------------------------------------ helpers


def _make_client(mock_openai: AsyncOpenAI) -> LLMClient:
    """创建一个重试不等待的 LLMClient，注入 mock 底层 client。"""
    return LLMClient(
        api_key="test-key",
        model="test-model",
        max_retries=3,
        retry_min_wait=0.0,
        retry_max_wait=0.0,
        client=mock_openai,
    )


def _fake_chat_completion(
    content: str = "hello",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
):
    """构造一个看起来像 ChatCompletion 的对象。"""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                index=0,
                message=SimpleNamespace(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        model="test-model",
    )


def _fake_chunk(content: str = "", usage=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                index=0,
                delta=SimpleNamespace(content=content),
                finish_reason=None,
            )
        ],
        usage=usage,
    )


class _AsyncIter:
    """将列表包装成 async iterator，模拟流式响应。"""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _make_mock_openai() -> MagicMock:
    """mock 一个 AsyncOpenAI，支持 client.chat.completions.create。"""
    mock = MagicMock(spec=AsyncOpenAI)
    mock.chat = MagicMock()
    mock.chat.completions = MagicMock()
    mock.chat.completions.create = AsyncMock()
    return mock


def _timeout_error() -> APITimeoutError:
    # openai>=1.x 的 APITimeoutError 要求一个 request 参数
    return APITimeoutError(request=httpx.Request("POST", "https://x/v1/chat/completions"))


# --------------------------------------------------------------------- chat


@pytest.mark.asyncio
async def test_chat_success_logs_tokens(caplog):
    mock = _make_mock_openai()
    mock.chat.completions.create.return_value = _fake_chat_completion(
        content="hi", prompt_tokens=42, completion_tokens=7
    )
    client = _make_client(mock)

    with caplog.at_level(logging.INFO, logger="llm.client"):
        resp = await client.chat([{"role": "user", "content": "ping"}])

    assert resp.choices[0].message.content == "hi"
    mock.chat.completions.create.assert_awaited_once()
    call_kwargs = mock.chat.completions.create.await_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["stream"] is False
    assert any("prompt_tokens=42" in r.message for r in caplog.records)
    assert any("completion_tokens=7" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_chat_retries_on_timeout_then_succeeds():
    mock = _make_mock_openai()
    mock.chat.completions.create.side_effect = [
        _timeout_error(),
        _timeout_error(),
        _fake_chat_completion(content="ok"),
    ]
    client = _make_client(mock)

    resp = await client.chat([{"role": "user", "content": "x"}])

    assert resp.choices[0].message.content == "ok"
    assert mock.chat.completions.create.await_count == 3


@pytest.mark.asyncio
async def test_chat_gives_up_after_max_retries():
    mock = _make_mock_openai()
    mock.chat.completions.create.side_effect = _timeout_error()
    client = _make_client(mock)

    with pytest.raises(APITimeoutError):
        await client.chat([{"role": "user", "content": "x"}])

    assert mock.chat.completions.create.await_count == 3


@pytest.mark.asyncio
async def test_chat_does_not_retry_non_retryable_error():
    mock = _make_mock_openai()
    mock.chat.completions.create.side_effect = AuthenticationError(
        message="bad key",
        response=httpx.Response(
            401, request=httpx.Request("POST", "https://x/v1/chat/completions")
        ),
        body=None,
    )
    client = _make_client(mock)

    with pytest.raises(AuthenticationError):
        await client.chat([{"role": "user", "content": "x"}])

    assert mock.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_chat_retries_on_rate_limit():
    mock = _make_mock_openai()
    rate_limit = RateLimitError(
        message="too fast",
        response=httpx.Response(
            429, request=httpx.Request("POST", "https://x/v1/chat/completions")
        ),
        body=None,
    )
    mock.chat.completions.create.side_effect = [
        rate_limit,
        _fake_chat_completion(content="ok"),
    ]
    client = _make_client(mock)

    resp = await client.chat([{"role": "user", "content": "x"}])
    assert resp.choices[0].message.content == "ok"
    assert mock.chat.completions.create.await_count == 2


# ------------------------------------------------------------------- stream


@pytest.mark.asyncio
async def test_stream_yields_chunks_and_logs_usage(caplog):
    chunks = [
        _fake_chunk(content="he"),
        _fake_chunk(content="llo"),
        _fake_chunk(
            content="",
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
        ),
    ]
    mock = _make_mock_openai()
    mock.chat.completions.create.return_value = _AsyncIter(chunks)
    client = _make_client(mock)

    collected = []
    with caplog.at_level(logging.INFO, logger="llm.client"):
        async for chunk in client.stream([{"role": "user", "content": "hi"}]):
            if chunk.choices and chunk.choices[0].delta.content:
                collected.append(chunk.choices[0].delta.content)

    assert "".join(collected) == "hello"
    create_kwargs = mock.chat.completions.create.await_args.kwargs
    assert create_kwargs["stream"] is True
    assert create_kwargs["stream_options"] == {"include_usage": True}
    assert any(
        "prompt_tokens=3" in r.message and "completion_tokens=2" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_stream_retries_connection_then_succeeds():
    mock = _make_mock_openai()
    mock.chat.completions.create.side_effect = [
        _timeout_error(),
        _AsyncIter([_fake_chunk(content="ok")]),
    ]
    client = _make_client(mock)

    out = []
    async for chunk in client.stream([{"role": "user", "content": "hi"}]):
        if chunk.choices and chunk.choices[0].delta.content:
            out.append(chunk.choices[0].delta.content)

    assert out == ["ok"]
    assert mock.chat.completions.create.await_count == 2


# --------------------------------------------------------------- constructor


def test_constructor_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMClient()


def test_constructor_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    c = LLMClient()
    assert c.api_key == "k"
    assert c.base_url == "https://api.deepseek.com/v1"
    assert c.model == "deepseek-chat"
