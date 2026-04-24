"""学段 & 人设 Listing API 测试。"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Stages ──────────────────────────────────────────────────


class TestStagesAPI:
    async def test_list_stages(self, client: AsyncClient) -> None:
        resp = await client.get("/api/stages")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 6
        ids = {s["id"] for s in data}
        assert ids == {"p_lower", "p_middle", "p_upper", "j_lower", "j_upper", "h"}
        # 概要字段齐全
        for s in data:
            assert "name" in s
            assert "grade_range" in s
            assert "age_range" in s

    async def test_get_stage_detail(self, client: AsyncClient) -> None:
        resp = await client.get("/api/stages/p_lower")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "p_lower"
        assert "cognitive_features" in data
        assert "teaching_implications" in data

    async def test_get_stage_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/stages/nonexistent")
        assert resp.status_code == 404


# ── Personas ────────────────────────────────────────────────


class TestPersonasAPI:
    async def test_list_all_personas(self, client: AsyncClient) -> None:
        resp = await client.get("/api/personas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 18
        # 概要字段齐全
        for p in data:
            assert "id" in p
            assert "name" in p
            assert "stage_id" in p
            assert "subject_level" in p

    async def test_filter_by_stage(self, client: AsyncClient) -> None:
        resp = await client.get("/api/personas", params={"stage_id": "p_lower"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert all(p["stage_id"] == "p_lower" for p in data)

    async def test_filter_by_level(self, client: AsyncClient) -> None:
        resp = await client.get("/api/personas", params={"subject_level": "优秀"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert all(p["subject_level"] == "优秀" for p in data)

    async def test_filter_combined(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/personas",
            params={"stage_id": "j_upper", "subject_level": "优秀"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert all(p["stage_id"] == "j_upper" and p["subject_level"] == "优秀" for p in data)

    async def test_get_persona_by_name(self, client: AsyncClient) -> None:
        # 先拿到一个名字
        all_resp = await client.get("/api/personas")
        name = all_resp.json()[0]["name"]
        resp = await client.get(f"/api/personas/{name}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name
        # 完整字段
        assert "personality" in resp.json()
        assert "catchphrases" in resp.json()

    async def test_get_persona_by_id(self, client: AsyncClient) -> None:
        all_resp = await client.get("/api/personas")
        pid = all_resp.json()[0]["id"]
        resp = await client.get(f"/api/personas/{pid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pid

    async def test_get_persona_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/personas/不存在的人")
        assert resp.status_code == 404
