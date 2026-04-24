"""学段 & 人设 Listing API 测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from schemas.lesson import LessonMeta


SAMPLE_META_JSON = {
    "subject": "数学",
    "grade": "三年级",
    "topic": "分数的初步认识",
    "objectives": ["理解几分之一的含义"],
    "key_points": ["几分之一的含义"],
    "difficult_points": ["理解平均分是分数的基础"],
}


def assert_wrapped(resp_json):
    assert resp_json["code"] == 0
    assert resp_json["message"] == "ok"
    assert isinstance(resp_json["request_id"], str)
    return resp_json["data"]


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Stages ──────────────────────────────────────────────────


class TestStagesAPI:
    async def test_list_stages(self, client: AsyncClient) -> None:
        resp = await client.get("/api/stages")
        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
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
        data = assert_wrapped(resp.json())
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
        data = assert_wrapped(resp.json())
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
        data = assert_wrapped(resp.json())
        assert len(data) == 3
        assert all(p["stage_id"] == "p_lower" for p in data)

    async def test_filter_by_level(self, client: AsyncClient) -> None:
        resp = await client.get("/api/personas", params={"subject_level": "优秀"})
        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
        assert len(data) >= 1
        assert all(p["subject_level"] == "优秀" for p in data)

    async def test_filter_combined(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/personas",
            params={"stage_id": "j_upper", "subject_level": "优秀"},
        )
        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
        assert len(data) >= 1
        assert all(p["stage_id"] == "j_upper" and p["subject_level"] == "优秀" for p in data)

    async def test_get_persona_by_name(self, client: AsyncClient) -> None:
        # 先拿到一个名字
        all_resp = await client.get("/api/personas")
        name = assert_wrapped(all_resp.json())[0]["name"]
        resp = await client.get(f"/api/personas/{name}")
        assert resp.status_code == 200
        assert assert_wrapped(resp.json())["name"] == name
        # 完整字段
        assert "personality" in assert_wrapped(resp.json())
        assert "catchphrases" in assert_wrapped(resp.json())

    async def test_get_persona_by_id(self, client: AsyncClient) -> None:
        all_resp = await client.get("/api/personas")
        pid = assert_wrapped(all_resp.json())[0]["id"]
        resp = await client.get(f"/api/personas/{pid}")
        assert resp.status_code == 200
        assert assert_wrapped(resp.json())["id"] == pid

    async def test_get_persona_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/personas/不存在的人")
        assert resp.status_code == 404


# ── Lessons ─────────────────────────────────────────────────


class TestLessonsAPI:
    @patch("api.lessons.index_lesson", return_value=5)
    @patch("api.lessons.extract_lesson_meta")
    @patch("api.lessons.parse_bytes", return_value="教案纯文本")
    async def test_upload_lesson(
        self,
        mock_parse: MagicMock,
        mock_extract: AsyncMock,
        mock_index: MagicMock,
        client: AsyncClient,
    ) -> None:
        mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)
        resp = await client.post(
            "/api/lessons/upload",
            files={"file": ("test.md", b"# Test", "text/markdown")},
        )
        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
        assert data["lesson_id"]
        assert data["subject"] == "数学"
        assert "meta" not in data

    @patch("api.lessons.index_lesson", return_value=5)
    @patch("api.lessons.extract_lesson_meta")
    @patch("api.lessons.parse_bytes", return_value="教案纯文本")
    async def test_get_lesson(
        self,
        mock_parse: MagicMock,
        mock_extract: AsyncMock,
        mock_index: MagicMock,
        client: AsyncClient,
    ) -> None:
        mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)
        upload_resp = await client.post(
            "/api/lessons/upload",
            files={"file": ("test.md", b"# Test", "text/markdown")},
        )
        lesson_id = assert_wrapped(upload_resp.json())["lesson_id"]
        resp = await client.get(f"/api/lessons/{lesson_id}")
        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
        assert data["lesson_id"] == lesson_id
        assert data["meta"]["subject"] == "数学"

    async def test_get_lesson_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/lessons/nonexistent")
        assert resp.status_code == 404

    async def test_upload_unsupported_format(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/lessons/upload",
            files={"file": ("test.docx", b"content", "application/octet-stream")},
        )
        assert resp.status_code == 400
