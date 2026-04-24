"""FastAPI entrypoint for EchoClass backend.

EchoClass 后端入口。Role A 创建初版，日常维护归 Role B。
Role A 追加 router 注册时请与 B 同步。

当前已注册的路由：
- GET /health — 健康检查
- GET /api/stages — 学段列表
- GET /api/stages/{id} — 学段详情
- GET /api/personas — 人设列表（支持过滤）
- GET /api/personas/{name_or_id} — 人设详情
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.lessons import router as lessons_router
from api.personas import router as personas_router
from api.stages import router as stages_router

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


app.include_router(lessons_router)
app.include_router(stages_router)
app.include_router(personas_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. 返回 {"status": "ok"}."""
    return {"status": "ok"}
