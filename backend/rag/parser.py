"""Lesson file parser — PDF / Markdown / TXT → plain text.

使用 pymupdf4llm 将 PDF 转为 Markdown 格式纯文本，
Markdown 和 TXT 直接读取。

PDF 解析统一走 ``pymupdf.open(stream=...)`` 内存流，避免 ``tempfile.NamedTemporaryFile``
在 Windows 下独占写导致 ``pymupdf4llm.to_markdown(path)`` 二次打开时抛
``PermissionError`` 的跨平台 bug（详见 issue #101）。
"""

from __future__ import annotations

import logging
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
    """使用 pymupdf4llm 将 PDF 转为 Markdown 文本。

    用 ``pymupdf.open(path)`` 显式拿到 Document 后传给 ``to_markdown``，
    与 ``_parse_pdf_bytes`` 保持同一调用契约（都用 Document 而非路径），
    便于 mock 与跨平台行为一致。
    """
    import pymupdf  # lazy import to avoid heavy load on startup
    import pymupdf4llm

    doc = pymupdf.open(str(path))
    try:
        text = pymupdf4llm.to_markdown(doc)
    finally:
        doc.close()
    logger.info("Parsed PDF %s → %d chars", path.name, len(text))
    return text


def _parse_pdf_bytes(content: bytes) -> str:
    """将 PDF 字节流通过 pymupdf 内存流解析为 Markdown。

    免落盘，跨平台一致；规避 Windows 上 ``NamedTemporaryFile`` 独占写
    + ``pymupdf4llm.to_markdown(path)`` 二次打开导致的 ``PermissionError``。
    """
    import pymupdf
    import pymupdf4llm

    doc = pymupdf.open(stream=content, filetype="pdf")
    try:
        text = pymupdf4llm.to_markdown(doc)
    finally:
        doc.close()
    logger.info("Parsed PDF bytes → %d chars", len(text))
    return text
