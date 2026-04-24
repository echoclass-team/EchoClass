"""API success response helpers."""
from __future__ import annotations

from uuid import uuid4

from schemas.api import ApiResponse


def ok_response(data) -> ApiResponse:
    return ApiResponse(code=0, message="ok", data=data, request_id=uuid4().hex)
