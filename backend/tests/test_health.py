"""Smoke test for /health endpoint."""
from __future__ import annotations

import httpx
import pytest

from main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
