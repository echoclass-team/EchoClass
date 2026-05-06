"""LLM 客户端封装。

统一封装 OpenAI 兼容接口的调用，提供重试、超时、token 使用日志。

当前默认后端为 ChatECNU ecnu-max（华东师范大学大模型平台），
也可通过环境变量切换到 DeepSeek / Qwen 等其它 OpenAI 兼容服务。

典型用法::

    from llm.client import LLMClient

    client = LLMClient()  # 从 env 读 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL

    # 非流式调用
    resp = await client.chat([{"role": "user", "content": "你好"}])
    print(resp.choices[0].message.content)

    # 流式调用
    async for chunk in client.stream([{"role": "user", "content": "你好"}]):
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            print(delta, end="", flush=True)
"""

from __future__ import annotations

import logging
import os
import time
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

# ChatECNU ecnu-max 处理整篇教案 / 多 student 并发 spawn 时
# 单次响应可达 60s+，30s 超时下并发 spawn 必触发 APITimeoutError，
# 故默认提升至 120s，给 retry 留出余量。
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_MIN_WAIT = 1.0
DEFAULT_RETRY_MAX_WAIT = 10.0


class LLMClient:
    """对 OpenAI 兼容 API 的薄封装。

    当前默认连接 ChatECNU ecnu-max，也可通过参数或环境变量切换到任意 OpenAI 兼容服务。

    Parameters
    ----------
    api_key : str, optional
        覆盖 env OPENAI_API_KEY。
    base_url : str, optional
        覆盖 env OPENAI_BASE_URL（默认 ChatECNU: https://chat.ecnu.edu.cn/open/api/v1）。
    model : str, optional
        覆盖 env LLM_MODEL（默认 ecnu-max）。
    timeout : float
        单次 HTTP 超时（秒），默认 30。
    max_retries : int
        可重试异常的最大尝试次数，默认 3。
    retry_min_wait / retry_max_wait : float
        tenacity 指数退避的下/上界（秒）。
    client : AsyncOpenAI, optional
        注入已有客户端实例（主要用于测试 mock）。

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
        self.model = model or os.getenv("LLM_MODEL", "ecnu-max")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait

        if client is not None:
            self._client = client
        else:
            # 允许无 key 构造：很多调用方（FastAPI 路由、测试 fixture）会先构造
            # ``LLMClient()`` 再决定是否走 mock；构造期就抛会让 mock 也跑不起来
            # （bug #144：CI 因此整组挂掉）。改为只在真的发请求时校验。
            # 构造 ``AsyncOpenAI`` 时若 key 缺失填占位串，让 SDK 接受；任何真实
            # 调用都会先经过 ``_require_api_key()`` 抛出明确错误，行为对生产无变化。
            self._client = AsyncOpenAI(
                api_key=self.api_key or "missing-api-key",
                base_url=self.base_url,
                timeout=timeout,
            )

    def _require_api_key(self) -> None:
        """在真实发起请求前校验 API key；缺失则抛 ``ValueError``。

        延迟到调用现场才检查，使 ``LLMClient()`` 构造在 CI / 测试 mock 场景下
        总能成功；任何真实 ``chat()`` / ``stream()`` 路径仍会立刻 fail-fast。
        """
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required (pass api_key= or set env OPENAI_API_KEY)"
            )

    # ---------------------------------------------------------------- chat

    async def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatCompletion:
        """非流式 chat completion；含重试 + token 日志。"""
        self._require_api_key()
        model = kwargs.pop("model", self.model)
        async for attempt in self._retrying():
            with attempt:
                t0 = time.perf_counter()
                resp: ChatCompletion = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=False,
                    **kwargs,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                self._log_usage("chat", model, resp.usage, latency_ms=latency_ms)
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
        self._require_api_key()
        model = kwargs.pop("model", self.model)
        # 让服务端在最后一个 chunk 里带 usage（OpenAI 兼容扩展）
        stream_options = kwargs.pop("stream_options", {"include_usage": True})

        t0 = time.perf_counter()
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
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self._log_usage_raw(
                "stream", model, prompt_tokens, completion_tokens, latency_ms=latency_ms
            )

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
    def _log_usage(
        call: str, model: str, usage: Any, *, latency_ms: int | None = None
    ) -> None:
        prompt = getattr(usage, "prompt_tokens", None) if usage else None
        completion = getattr(usage, "completion_tokens", None) if usage else None
        LLMClient._log_usage_raw(call, model, prompt, completion, latency_ms=latency_ms)

    @staticmethod
    def _log_usage_raw(
        call: str,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        *,
        latency_ms: int | None = None,
    ) -> None:
        logger.info(
            "llm.%s model=%s prompt_tokens=%s completion_tokens=%s latency_ms=%s",
            call,
            model,
            prompt_tokens,
            completion_tokens,
            latency_ms,
            extra={
                "event": "llm_call",
                "call": call,
                "model": model,
                "token_in": prompt_tokens,
                "token_out": completion_tokens,
                "latency_ms": latency_ms,
            },
        )
