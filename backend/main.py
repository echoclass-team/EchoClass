"""FastAPI entrypoint for EchoClass backend.

Scaffold for W1-01 (Issue #16). Role A 创建初版；合并后日常维护归 Role B。
Role A 只应在此文件追加 router 注册，变更前请与 B 同步。
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(
    title="EchoClass Backend",
    version="0.1.0",
    description="AI-powered virtual classroom for pre-service teachers.",
)

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. 返回 {"status": "ok"}."""
    return {"status": "ok"}
