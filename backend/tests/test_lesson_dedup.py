"""教案去重 API 测试 (#132)。

验证 ``POST /api/lessons/upload`` 在同一用户重复上传完全相同内容的文件时：

- 第二次请求**不再调用** parser / extractor / indexer（避免重复消耗 LLM token
  与向量库空间）
- 响应里 ``reused=True``，``lesson_id`` 与首次相同
- 内容不同 → 仍走完整解析流程，``reused=False``
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.deps import CurrentUser, get_current_user
from schemas.lesson import LessonMeta


SAMPLE_META_JSON = {
    "subject": "数学",
    "grade": "三年级",
    "topic": "分数的初步认识",
    "objectives": ["理解分数概念", "认识分子分母", "比较简单分数"],
    "key_points": ["分数表示部分与整体的关系", "分母不能为 0"],
    "difficult_points": ["抽象到具体的转化"],
}


def _fake_lesson_row(lesson_id: str, content_hash: str) -> SimpleNamespace:
    """构造一个最小化的 Lesson row 替身，覆盖 dedup 路径需要读到的字段。"""
    meta = LessonMeta(**SAMPLE_META_JSON)
    return SimpleNamespace(
        id=lesson_id,
        owner_id="test-user",
        content_hash=content_hash,
        filename="lesson.md",
        title=meta.topic,
        meta_json=meta.model_dump_json(),
        text_length=42,
        chunk_count=3,
    )


@pytest.fixture(autouse=True)
def _clear_inmem_store():
    """避免上一条测试残留的内存缓存影响 dedup 命中判断。"""
    from api.lessons import _store

    _store.clear()
    yield
    _store.clear()


@pytest.fixture(autouse=True)
def _auth_override():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user", username="tester"
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


async def _post_upload(content: bytes, filename: str = "lesson.md") -> httpx.Response:
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/lessons/upload",
            files={"file": (filename, content, "text/markdown")},
        )


@patch("api.lessons.save_lesson")
@patch("api.lessons.get_lesson_by_hash", return_value=None)
@patch("api.lessons.index_lesson", return_value=5)
@patch("api.lessons.extract_lesson_meta")
@patch("api.lessons.parse_bytes", return_value="教案纯文本")
async def test_first_upload_is_not_reused(
    mock_parse: MagicMock,
    mock_extract: AsyncMock,
    mock_index: MagicMock,
    mock_get_by_hash: MagicMock,
    mock_save: MagicMock,
) -> None:
    """首次上传：dedup miss → 走完整解析路径，``reused=False``。"""
    mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)

    resp = await _post_upload("# Lesson v1\n\n第一次上传".encode("utf-8"))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reused"] is False
    assert data["subject"] == "数学"

    mock_get_by_hash.assert_called_once()  # 进了 dedup 检查
    mock_parse.assert_called_once()  # 但是 miss，走完整路径
    mock_extract.assert_awaited_once()
    mock_index.assert_called_once()
    mock_save.assert_called_once()


@patch("api.lessons.save_lesson")
@patch("api.lessons.index_lesson", return_value=5)
@patch("api.lessons.extract_lesson_meta")
@patch("api.lessons.parse_bytes", return_value="教案纯文本")
async def test_second_upload_same_content_is_reused(
    mock_parse: MagicMock,
    mock_extract: AsyncMock,
    mock_index: MagicMock,
    mock_save: MagicMock,
) -> None:
    """同一文件二次上传：dedup hit → 跳过 parser/extractor/indexer，``reused=True``，
    ``lesson_id`` 与已存在记录一致。"""
    cached = _fake_lesson_row(lesson_id="cached-lesson-id", content_hash="ignored")

    with patch("api.lessons.get_lesson_by_hash", return_value=cached) as mock_get:
        resp = await _post_upload("# Lesson v1\n\n第一次上传".encode("utf-8"))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reused"] is True
    assert data["lesson_id"] == "cached-lesson-id"
    assert data["topic"] == SAMPLE_META_JSON["topic"]
    assert data["objectives"] == SAMPLE_META_JSON["objectives"]

    mock_get.assert_called_once()
    mock_parse.assert_not_called()
    mock_extract.assert_not_awaited()
    mock_index.assert_not_called()
    mock_save.assert_not_called()


@patch("api.lessons.save_lesson")
@patch("api.lessons.get_lesson_by_hash", return_value=None)
@patch("api.lessons.index_lesson", return_value=5)
@patch("api.lessons.extract_lesson_meta")
@patch("api.lessons.parse_bytes", return_value="教案纯文本")
async def test_different_content_not_deduped(
    mock_parse: MagicMock,
    mock_extract: AsyncMock,
    mock_index: MagicMock,
    mock_get_by_hash: MagicMock,
    mock_save: MagicMock,
) -> None:
    """两次上传内容不同 → hash 各异，两次都走完整流程，``reused=False``。"""
    mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)

    resp1 = await _post_upload("# Lesson A\n\n内容 A".encode("utf-8"))
    resp2 = await _post_upload("# Lesson B\n\n内容 B".encode("utf-8"))

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["data"]["reused"] is False
    assert resp2.json()["data"]["reused"] is False

    # 两次上传两次 dedup 检查；每次都 miss → 两次完整流程
    assert mock_get_by_hash.call_count == 2
    assert mock_parse.call_count == 2
    assert mock_extract.await_count == 2
    assert mock_index.call_count == 2
    assert mock_save.call_count == 2


@patch("api.lessons.save_lesson")
@patch("api.lessons.index_lesson", return_value=5)
@patch("api.lessons.extract_lesson_meta")
@patch("api.lessons.parse_bytes", return_value="教案纯文本")
async def test_corrupt_meta_falls_back_to_full_pipeline(
    mock_parse: MagicMock,
    mock_extract: AsyncMock,
    mock_index: MagicMock,
    mock_save: MagicMock,
) -> None:
    """命中 hash 但 ``meta_json`` 损坏 → 降级走完整解析路径，``reused=False``。"""
    mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)
    cached = _fake_lesson_row("legacy-id", "ignored")
    cached.meta_json = "{not valid json"

    with patch("api.lessons.get_lesson_by_hash", return_value=cached):
        resp = await _post_upload("# Lesson\n\n损坏 meta_json 的旧记录".encode("utf-8"))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reused"] is False
    mock_parse.assert_called_once()
    mock_save.assert_called_once()
