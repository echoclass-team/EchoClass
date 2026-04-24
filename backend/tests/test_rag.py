"""RAG pipeline tests — parser / extractor / indexer / API (Issue #19).

所有 LLM 调用和 PDF 解析均 mock，验证：
1. parser: MD/TXT 正确读取，PDF 走 pymupdf4llm，不支持格式抛 ValueError。
2. extractor: LLM JSON → LessonMeta 正确解析，包含 code block 包裹和裸 JSON。
3. indexer: chunk_text 正确切片，index_lesson 写入 Chroma。
4. API: POST /api/lessons/upload 和 GET /api/lessons/{id} 联通。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from rag.extractor import _parse_meta, extract_lesson_meta
from rag.indexer import chunk_text, index_lesson, query_lesson
from rag.parser import SUPPORTED_EXTENSIONS, parse_bytes, parse_file
from schemas.lesson import LessonMeta, LessonRecord

# ============================================================ Parser


class TestParser:
    """parser.py 单元测试。"""

    def test_parse_md_file(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("# 标题\n\n正文内容", encoding="utf-8")
        result = parse_file(md)
        assert "标题" in result
        assert "正文内容" in result

    def test_parse_txt_file(self, tmp_path: Path) -> None:
        txt = tmp_path / "test.txt"
        txt.write_text("纯文本教案", encoding="utf-8")
        result = parse_file(txt)
        assert result == "纯文本教案"

    def test_parse_bytes_md(self) -> None:
        content = "# Markdown 教案".encode("utf-8")
        result = parse_bytes(content, "lesson.md")
        assert "Markdown 教案" in result

    def test_parse_bytes_txt(self) -> None:
        content = "文本教案".encode("utf-8")
        result = parse_bytes(content, "lesson.txt")
        assert result == "文本教案"

    def test_unsupported_extension_file(self, tmp_path: Path) -> None:
        docx = tmp_path / "test.docx"
        docx.write_text("content")
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_file(docx)

    def test_unsupported_extension_bytes(self) -> None:
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_bytes(b"content", "test.docx")

    def test_supported_extensions_set(self) -> None:
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS

    @patch.dict(
        "sys.modules",
        {
            "pymupdf4llm": MagicMock(
                to_markdown=MagicMock(return_value="PDF 转换后的文本")
            )
        },
    )
    def test_parse_pdf_file(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        result = parse_file(pdf)
        assert result == "PDF 转换后的文本"

    @patch.dict(
        "sys.modules",
        {
            "pymupdf4llm": MagicMock(
                to_markdown=MagicMock(return_value="PDF bytes 解析结果")
            )
        },
    )
    def test_parse_pdf_bytes(self) -> None:
        result = parse_bytes(b"%PDF-1.4 fake", "test.pdf")
        assert result == "PDF bytes 解析结果"


# ============================================================ Extractor


SAMPLE_META_JSON = {
    "subject": "数学",
    "grade": "三年级",
    "topic": "分数的初步认识",
    "objectives": ["理解几分之一的含义", "会读写几分之一", "比较大小"],
    "key_points": ["几分之一的含义", "分数各部分名称"],
    "difficult_points": ["理解平均分是分数的基础"],
}


class TestExtractor:
    """extractor.py 单元测试。"""

    def test_parse_meta_bare_json(self) -> None:
        raw = json.dumps(SAMPLE_META_JSON, ensure_ascii=False)
        meta = _parse_meta(raw)
        assert meta.subject == "数学"
        assert meta.grade == "三年级"
        assert len(meta.objectives) == 3

    def test_parse_meta_code_block(self) -> None:
        raw = f"以下是结果：\n```json\n{json.dumps(SAMPLE_META_JSON, ensure_ascii=False)}\n```"
        meta = _parse_meta(raw)
        assert meta.topic == "分数的初步认识"
        assert len(meta.key_points) == 2

    def test_parse_meta_no_json_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON found"):
            _parse_meta("这里没有任何 JSON")

    def test_parse_meta_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="JSON 解析失败"):
            _parse_meta("{invalid json content}")

    async def test_extract_lesson_meta_calls_llm(self) -> None:
        mock_message = MagicMock()
        mock_message.content = json.dumps(SAMPLE_META_JSON, ensure_ascii=False)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=mock_resp)

        meta = await extract_lesson_meta(mock_llm, "教案文本内容")

        mock_llm.chat.assert_called_once()
        assert isinstance(meta, LessonMeta)
        assert meta.subject == "数学"

    async def test_extract_truncates_long_text(self) -> None:
        mock_message = MagicMock()
        mock_message.content = json.dumps(SAMPLE_META_JSON, ensure_ascii=False)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=mock_resp)

        long_text = "A" * 20000
        await extract_lesson_meta(mock_llm, long_text, max_chars=5000)

        # 验证 prompt 中文本被截断
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_content = messages[0]["content"]
        # 截断后不应包含完整 20000 个 A
        assert len(system_content) < 20000


# ============================================================ Indexer


class TestIndexer:
    """indexer.py 单元测试。"""

    def test_chunk_text_basic(self) -> None:
        text = "A" * 3000
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        assert len(chunks) >= 3
        # 每片不超过 chunk_size
        for c in chunks:
            assert len(c) <= 1000

    def test_chunk_text_short(self) -> None:
        text = "短文本"
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == "短文本"

    def test_chunk_text_empty(self) -> None:
        assert chunk_text("") == []

    def test_chunk_text_overlap(self) -> None:
        text = "ABCDEFGHIJ" * 100  # 1000 chars
        chunks = chunk_text(text, chunk_size=400, overlap=50)
        # 相邻 chunks 应有重叠
        if len(chunks) >= 2:
            tail_of_first = chunks[0][-50:]
            head_of_second = chunks[1][:50]
            assert tail_of_first == head_of_second

    def test_index_lesson_to_chroma(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            count = index_lesson("test_001", "A" * 3000, persist_dir=tmpdir)
            assert count >= 3

    def test_query_lesson_from_chroma(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            text = "分数是表示部分与整体关系的数。" * 200
            index_lesson("test_002", text, persist_dir=tmpdir)
            results = query_lesson("分数", lesson_id="test_002", persist_dir=tmpdir)
            assert len(results) > 0
            assert any("分数" in r for r in results)

    def test_index_empty_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            count = index_lesson("test_empty", "", persist_dir=tmpdir)
            assert count == 0


# ============================================================ Schema


class TestLessonSchema:
    """schemas/lesson.py 单元测试。"""

    def test_lesson_meta_creation(self) -> None:
        meta = LessonMeta(**SAMPLE_META_JSON)
        assert meta.subject == "数学"
        assert len(meta.objectives) == 3

    def test_lesson_record_creation(self) -> None:
        meta = LessonMeta(**SAMPLE_META_JSON)
        record = LessonRecord(
            lesson_id="abc123",
            filename="test.md",
            meta=meta,
            text_length=5000,
            chunk_count=5,
        )
        assert record.lesson_id == "abc123"
        dump = record.model_dump()
        assert dump["meta"]["subject"] == "数学"


# ============================================================ API


class TestLessonAPI:
    """API 路由集成测试（mock LLM + Chroma）。"""

    @patch("api.lessons.index_lesson", return_value=5)
    @patch("api.lessons.extract_lesson_meta")
    @patch("api.lessons.parse_bytes", return_value="教案纯文本")
    async def test_upload_lesson(
        self,
        mock_parse: MagicMock,
        mock_extract: AsyncMock,
        mock_index: MagicMock,
    ) -> None:
        mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)

        from main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/lessons/upload",
                files={"file": ("test.md", b"# Test", "text/markdown")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "lesson_id" in data
        assert data["subject"] == "数学"
        assert len(data["objectives"]) == 3

    @patch("api.lessons.index_lesson", return_value=5)
    @patch("api.lessons.extract_lesson_meta")
    @patch("api.lessons.parse_bytes", return_value="教案纯文本")
    async def test_get_lesson(
        self,
        mock_parse: MagicMock,
        mock_extract: AsyncMock,
        mock_index: MagicMock,
    ) -> None:
        mock_extract.return_value = LessonMeta(**SAMPLE_META_JSON)

        from main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # 先上传
            resp = await client.post(
                "/api/lessons/upload",
                files={"file": ("test.md", b"# Test", "text/markdown")},
            )
            lesson_id = resp.json()["lesson_id"]

            # 再查询
            resp2 = await client.get(f"/api/lessons/{lesson_id}")

        assert resp2.status_code == 200
        data = resp2.json()
        assert data["lesson_id"] == lesson_id
        assert data["meta"]["subject"] == "数学"

    async def test_get_lesson_not_found(self) -> None:
        from main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/lessons/nonexistent")
        assert resp.status_code == 404

    async def test_upload_unsupported_format(self) -> None:
        from main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/lessons/upload",
                files={"file": ("test.docx", b"content", "application/octet-stream")},
            )
        assert resp.status_code == 400
