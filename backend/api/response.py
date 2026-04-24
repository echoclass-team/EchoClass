"""API 响应包络辅助函数。

- ok_response：业务成功时包一层 ApiResponse（code=0, message="ok"）。
- http_exception_handler：全局 HTTPException 捕获，同样输出 ApiResponse 结构，
  让前端只需要一套 envelope 解析逻辑。
"""

from __future__ import annotations

from typing import TypeVar
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from schemas.api import ApiResponse

T = TypeVar("T")


def ok_response(data: T) -> ApiResponse[T]:
    """业务成功响应：code=0 / message=ok / data=payload。"""
    return ApiResponse(code=0, message="ok", data=data, request_id=uuid4().hex)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """全局 HTTPException → ApiResponse 错误包络。

    约定：
    - HTTP 状态码仍然保留（方便代理/监控区分）。
    - 响应体格式与成功一致：{code, message, data=null, request_id}。
    - code 直接使用 HTTP status code，便于调试；后续需要可映射为业务错误码。
    """
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    payload = ApiResponse(
        code=exc.status_code,
        message=detail,
        data=None,
        request_id=uuid4().hex,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
    )
