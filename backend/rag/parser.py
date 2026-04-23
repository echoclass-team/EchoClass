"""Lesson file parser — PDF / Markdown / TXT → plain text.

使用 pymupdf4llm 将 PDF 转为 Markdown 格式纯文本，
Markdown 和 TXT 直接读取。
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}


def parse_file(file_path: str | Path) -> str:
    """解析本地文件为纯文本。

    Parameters
    ----------
    file_path : str | Path
        支持 .pdf / .md / .txt

    Returns
    -------
    str
        解析后的纯文本内容。
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}"
        )

    if ext == ".pdf":
        return _parse_pdf(path)
    return path.read_text(encoding="utf-8")


def parse_bytes(content: bytes, filename: str) -> str:
    """解析上传的文件字节流为纯文本。

    Parameters
    ----------
    content : bytes
        文件内容。
    filename : str
        原始文件名（用于判断格式）。

    Returns
    -------
    str
        解析后的纯文本内容。
    """
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}"
        )

    if ext == ".pdf":
        return _parse_pdf_bytes(content)
    return content.decode("utf-8")


def _parse_pdf(path: Path) -> str:
    """使用 pymupdf4llm 将 PDF 转为 Markdown 文本。"""
    import pymupdf4llm  # lazy import to avoid heavy load on startup

    text = pymupdf4llm.to_markdown(str(path))
    logger.info("Parsed PDF %s → %d chars", path.name, len(text))
    return text


def _parse_pdf_bytes(content: bytes) -> str:
    """将 PDF 字节流写入临时文件后解析。"""
    import pymupdf4llm

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        text = pymupdf4llm.to_markdown(tmp.name)
    logger.info("Parsed PDF bytes → %d chars", len(text))
    return text
