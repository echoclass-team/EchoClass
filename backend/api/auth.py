"""认证路由：注册 + 登录（M3 #B1）。

对应 ``docs/api_contract.md §0.5.1``：
- ``POST /api/auth/register`` → ``{user_id}``
- ``POST /api/auth/login``    → ``{access_token, token_type}``
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth_utils import create_access_token, hash_password, verify_password
from api.response import ok_response
from db.engine import get_db
from db.models import User
from schemas.api import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---- request / response models ----

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)


class RegisterData(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginData(BaseModel):
    access_token: str
    token_type: str = "Bearer"


# ---- routes ----

@router.post("/register", response_model=ApiResponse[RegisterData])
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> ApiResponse[RegisterData]:  # noqa: B008
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("register: user=%s id=%s", user.username, user.id)
    return ok_response(RegisterData(user_id=user.id))


@router.post("/login", response_model=ApiResponse[LoginData])
def login(body: LoginRequest, db: Session = Depends(get_db)) -> ApiResponse[LoginData]:  # noqa: B008
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id, user.username)
    logger.info("login: user=%s id=%s", user.username, user.id)
    return ok_response(LoginData(access_token=token))
