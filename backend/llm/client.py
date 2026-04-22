"""LLM client wrapper.

统一封装 OpenAI 兼容接口（DeepSeek / Qwen / DashScope）的调用，
提供重试、超时、token 使用日志。

典型用法：

    from llm.client import LLMClient

    client = LLMClient()  # 从 env 读 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL

    # 一次性
    resp = await client.chat([{"role": "user", "content": "你好"}])
    print(resp.choices[0].message.content)

    # 流式
    async for chunk in client.stream([{"role": "user", "content": "你好"}]):
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            print(delta, end="", flush=True)
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# 遇到这些异常才重试；鉴权 / 参数错误立即抛出。
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
)

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_MIN_WAIT = 1.0
DEFAULT_RETRY_MAX_WAIT = 10.0


class LLMClient:
    """对 OpenAI 兼容 API 的薄封装。

    参数：
        api_key: 覆盖 env OPENAI_API_KEY
        base_url: 覆盖 env OPENAI_BASE_URL（DeepSeek 用 https://api.deepseek.com/v1 等）
        model: 覆盖 env LLM_MODEL
        timeout: 单次 HTTP 超时（秒），默认 30
        max_retries: 可重试异常的最大尝试次数，默认 3
        retry_min_wait / retry_max_wait: 指数退避的下/上界（秒）

    测试里常用 ``max_retries=3, retry_min_wait=0.0, retry_max_wait=0.0``
    让重试不等待。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_min_wait: float = DEFAULT_RETRY_MIN_WAIT,
        retry_max_wait: float = DEFAULT_RETRY_MAX_WAIT,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait

        if client is not None:
            self._client = client
        else:
            if not self.api_key:
                raise ValueError(
                    "OPENAI_API_KEY is required (pass api_key= or set env OPENAI_API_KEY)"
                )
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=timeout,
            )

    # ---------------------------------------------------------------- chat

    async def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatCompletion:
        """非流式 chat completion；含重试 + token 日志。"""
        model = kwargs.pop("model", self.model)
        async for attempt in self._retrying():
            with attempt:
                resp: ChatCompletion = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=False,
                    **kwargs,
                )
                self._log_usage("chat", model, resp.usage)
                return resp
        # AsyncRetrying(reraise=True) 下不会到这里；保险起见抛出
        raise RuntimeError("LLMClient.chat: unreachable")  # pragma: no cover

    # -------------------------------------------------------------- stream

    async def stream(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """流式 chat completion。

        连接阶段遇到可重试异常会重试；iteration 开始后若底层断开不重试
        （避免给上层吐重复内容）。
        """
        model = kwargs.pop("model", self.model)
        # 让服务端在最后一个 chunk 里带 usage（OpenAI 兼容扩展）
        stream_options = kwargs.pop("stream_options", {"include_usage": True})

        stream = await self._open_stream(
            model=model,
            messages=messages,
            stream_options=stream_options,
            extra_kwargs=kwargs,
        )

        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        try:
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                yield chunk
        finally:
            self._log_usage_raw("stream", model, prompt_tokens, completion_tokens)

    async def _open_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stream_options: dict[str, Any],
        extra_kwargs: dict[str, Any],
    ) -> AsyncIterator[ChatCompletionChunk]:
        """建立流式连接；仅对连接阶段应用重试。"""
        async for attempt in self._retrying():
            with attempt:
                return await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                    stream_options=stream_options,
                    **extra_kwargs,
                )
        raise RuntimeError("LLMClient._open_stream: unreachable")  # pragma: no cover

    # --------------------------------------------------------------- utils

    def _retrying(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=self.retry_min_wait,
                max=self.retry_max_wait,
            ),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            reraise=True,
        )

    @staticmethod
    def _log_usage(call: str, model: str, usage: Any) -> None:
        prompt = getattr(usage, "prompt_tokens", None) if usage else None
        completion = getattr(usage, "completion_tokens", None) if usage else None
        LLMClient._log_usage_raw(call, model, prompt, completion)

    @staticmethod
    def _log_usage_raw(
        call: str,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        logger.info(
            "llm.%s model=%s prompt_tokens=%s completion_tokens=%s",
            call,
            model,
            prompt_tokens,
            completion_tokens,
        )
