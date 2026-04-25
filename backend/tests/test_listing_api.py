"""学段 & 人设 Listing API 测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from api.lessons import _store, infer_stage_id_from_grade
from schemas.lesson import LessonMeta, LessonRecord


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
        # 错误响应也走 envelope：code=404, message 带 detail, data=None
        body = resp.json()
        assert body["code"] == 404
        assert "nonexistent" in body["message"]
        assert body["data"] is None
        assert isinstance(body["request_id"], str)


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
        assert all(
            p["stage_id"] == "j_upper" and p["subject_level"] == "优秀" for p in data
        )

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
    @pytest.fixture(autouse=True)
    def clean_lesson_store(self):
        original = _store.copy()
        _store.clear()
        yield
        _store.clear()
        _store.update(original)

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

    @pytest.mark.parametrize(
        ("grade", "expected"),
        [
            ("一年级", "p_lower"),
            ("小学二年级", "p_lower"),
            ("三年级", "p_middle"),
            ("小学四年级", "p_middle"),
            ("5年级", "p_upper"),
            ("P6", "p_upper"),
            ("七年级", "j_lower"),
            ("初二", "j_lower"),
            ("初中一年级", "j_lower"),
            ("J1", "j_lower"),
            ("九年级", "j_upper"),
            ("初三", "j_upper"),
            ("初中三年级", "j_upper"),
            ("J3", "j_upper"),
            ("高一", "h"),
            ("高中二年级", "h"),
            ("H2", "h"),
            ("高中", "h"),
        ],
    )
    def test_infer_stage_id_from_grade(self, grade: str, expected: str) -> None:
        assert infer_stage_id_from_grade(grade) == expected

    async def test_recommend_personas_for_lesson(self, client: AsyncClient) -> None:
        lesson_id = "lesson-p3"
        _store[lesson_id] = LessonRecord(
            lesson_id=lesson_id,
            filename="test.md",
            meta=LessonMeta(**SAMPLE_META_JSON),
        )

        resp = await client.get(f"/api/lessons/{lesson_id}/recommended-personas")

        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
        assert data["lesson_id"] == lesson_id
        assert data["stage_id"] == "p_middle"
        assert data["stage_name"]
        assert data["recommended_count"] == len(data["students"])
        assert data["persona_ids"] == [student["id"] for student in data["students"]]
        assert all(student["stage_id"] == "p_middle" for student in data["students"])

    async def test_recommend_personas_respects_count(self, client: AsyncClient) -> None:
        lesson_id = "lesson-count"
        _store[lesson_id] = LessonRecord(
            lesson_id=lesson_id,
            filename="test.md",
            meta=LessonMeta(**SAMPLE_META_JSON),
        )

        resp = await client.get(
            f"/api/lessons/{lesson_id}/recommended-personas",
            params={"count": 2},
        )

        assert resp.status_code == 200
        data = assert_wrapped(resp.json())
        assert data["recommended_count"] == 2
        assert len(data["students"]) == 2

    async def test_recommend_personas_lesson_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/lessons/nonexistent/recommended-personas")
        assert resp.status_code == 404

    async def test_recommend_personas_unknown_grade(self, client: AsyncClient) -> None:
        lesson_id = "lesson-unknown-grade"
        _store[lesson_id] = LessonRecord(
            lesson_id=lesson_id,
            filename="test.md",
            meta=LessonMeta(
                subject="数学",
                grade="火星年级",
                topic="分数的初步认识",
            ),
        )

        resp = await client.get(f"/api/lessons/{lesson_id}/recommended-personas")

        assert resp.status_code == 400
        assert "火星年级" in resp.json()["message"]
