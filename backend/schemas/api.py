"""通用 API response schema."""
from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(..., description="业务状态码")
    message: str = Field(..., description="提示信息")
    data: T | None = Field(default=None, description="响应数据")
    request_id: str | UUID = Field(..., description="请求追踪 ID")
