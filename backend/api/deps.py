"""共享依赖注入（M3 #B1）。

``get_current_user`` — 从 ``Authorization: Bearer <jwt>`` 解析当前用户。
受保护路由只需 ``Depends(get_current_user)``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth_utils import decode_access_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """从 JWT 解出的当前用户信息。"""

    id: str
    username: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")

    try:
        payload = decode_access_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token 无效")

    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id or not username:
        raise HTTPException(status_code=401, detail="Token claims 不完整")

    return CurrentUser(id=user_id, username=username)
