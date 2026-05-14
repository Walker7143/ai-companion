"""Utilities for extracting plain text from inbound document attachments."""

from __future__ import annotations

import json
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


DEFAULT_MAX_EXTRACT_CHARS = 180_000
DEFAULT_CHUNK_CHARS = 6_000
DEFAULT_CHUNK_OVERLAP = 250

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".htm",
    ".css",
    ".xml",
    ".ini",
    ".cfg",
    ".conf",
}
_OPENXML_EXTENSIONS = {".docx", ".xlsx", ".pptx"}
_SUPPORTED_EXTENSIONS = _TEXT_EXTENSIONS | _OPENXML_EXTENSIONS | {".pdf"}
_SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "text/markdown",
}


@dataclass(frozen=True)
class DocumentExtraction:
    """Text extraction result for one cached attachment."""

    path: str
    name: str
    media_type: str
    text: str = ""
    error: str = ""
    truncated: bool = False


def is_document_media(path: str, media_type: str = "") -> bool:
    """Return True when a cached media item should be treated as a document."""

    candidate = str(path or "").strip()
    if not candidate:
        return False

    media = str(media_type or "").strip().lower()
    if media.startswith(("image/", "audio/", "video/")):
        return False
    if media.startswith("text/") or media in _SUPPORTED_MIME_TYPES:
        return True

    ext = Path(candidate).suffix.lower()
    return ext in _SUPPORTED_EXTENSIONS


def extract_documents_from_media(
    media_urls: list[str],
    media_types: list[str] | None = None,
    *,
    max_chars_per_document: int = DEFAULT_MAX_EXTRACT_CHARS,
) -> list[DocumentExtraction]:
    """Extract text from all document-like media paths in a message."""

    media_types = media_types or []
    results: list[DocumentExtraction] = []
    for idx, raw_path in enumerate(media_urls or []):
        path = str(raw_path or "").strip()
        media_type = str(media_types[idx] if idx < len(media_types) else "" or "")
        if not is_document_media(path, media_type):
            continue
        results.append(
            extract_document_text(
                path,
                media_type=media_type,
                max_chars=max_chars_per_document,
            )
        )
    return results


def extract_document_text(
    path: str,
    *,
    media_type: str = "",
    max_chars: int = DEFAULT_MAX_EXTRACT_CHARS,
) -> DocumentExtraction:
    """Extract readable text from a local document path."""

    file_path = Path(path).expanduser()
    display_name = _display_name(file_path)
    media = str(media_type or mimetypes.guess_type(file_path.name)[0] or "").lower()

    if not file_path.exists() or not file_path.is_file():
        return DocumentExtraction(str(file_path), display_name, media, error="file_not_found")

    ext = file_path.suffix.lower()
    try:
        if ext in _TEXT_EXTENSIONS or media.startswith("text/") or media in {"application/json", "application/xml"}:
            text, truncated = _extract_text_file(file_path, max_chars=max_chars)
        elif ext == ".docx":
            text = _extract_docx(file_path)
            text, truncated = _limit_text(text, max_chars)
        elif ext == ".xlsx":
            text = _extract_xlsx(file_path)
            text, truncated = _limit_text(text, max_chars)
        elif ext == ".pptx":
            text = _extract_pptx(file_path)
            text, truncated = _limit_text(text, max_chars)
        elif ext == ".pdf" or media == "application/pdf":
            text = _extract_pdf(file_path)
            text, truncated = _limit_text(text, max_chars)
        else:
            return DocumentExtraction(
                str(file_path),
                display_name,
                media,
                error=f"unsupported_type:{ext or media or 'unknown'}",
            )
    except Exception as exc:  # noqa: BLE001 - return a user-visible extraction status.
        return DocumentExtraction(
            str(file_path),
            display_name,
            media,
            error=f"extract_failed:{type(exc).__name__}",
        )

    normalized = _normalize_text(text)
    if not normalized:
        return DocumentExtraction(
            str(file_path),
            display_name,
            media,
            error="no_extractable_text",
            truncated=truncated,
        )
    return DocumentExtraction(str(file_path), display_name, media, text=normalized, truncated=truncated)


def combine_document_texts(results: Iterable[DocumentExtraction]) -> tuple[str, list[str], bool]:
    """Combine successful document texts and return text, error notes, truncated flag."""

    sections: list[str] = []
    errors: list[str] = []
    truncated = False
    for item in results:
        if item.text:
            sections.append(f"### {item.name}\n{item.text}")
            truncated = truncated or item.truncated
        elif item.error:
            errors.append(f"{item.name}: {item.error}")
    return "\n\n".join(sections).strip(), errors, truncated


def split_text_chunks(
    text: str,
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into mostly paragraph-aligned chunks with light overlap."""

    cleaned = _normalize_text(text)
    if not cleaned:
        return []
    max_chars = max(1_000, int(max_chars or DEFAULT_CHUNK_CHARS))
    overlap = max(0, min(int(overlap or 0), max_chars // 4))
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    total = len(cleaned)
    while start < total:
        hard_end = min(total, start + max_chars)
        end = hard_end
        if hard_end < total:
            candidates = [
                cleaned.rfind("\n\n", start, hard_end),
                cleaned.rfind("\n", start, hard_end),
                cleaned.rfind("。", start, hard_end),
                cleaned.rfind(".", start, hard_end),
                cleaned.rfind(" ", start, hard_end),
            ]
            boundary = max(candidates)
            if boundary > start + int(max_chars * 0.55):
                end = boundary + 1
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= total:
            break
        next_start = max(end - overlap, start + 1)
        start = next_start
    return chunks


def _display_name(path: Path) -> str:
    name = path.name or "document"
    match = re.match(r"^doc_[0-9a-fA-F]{12}_(.+)$", name)
    return match.group(1) if match else name


def _limit_text(text: str, max_chars: int) -> tuple[str, bool]:
    max_chars = max(1, int(max_chars or DEFAULT_MAX_EXTRACT_CHARS))
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _normalize_text(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip()


def _extract_text_file(path: Path, *, max_chars: int) -> tuple[str, bool]:
    max_bytes = max(4_096, max_chars * 4)
    data = path.read_bytes()[: max_bytes + 1]
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    if b"\x00" in data[:1024]:
        raise ValueError("binary_text_file")

    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")

    text, char_truncated = _limit_text(text, max_chars)
    return text, truncated or char_truncated


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _paragraph_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        name = _local_name(node.tag)
        if name == "t" and node.text:
            parts.append(node.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _extract_docx(path: Path) -> str:
    lines: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for member in ("word/document.xml",):
            if member not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(member))
            for para in root.iter():
                if _local_name(para.tag) != "p":
                    continue
                line = _paragraph_text(para)
                if line:
                    lines.append(line)
    return "\n".join(lines)


def _extract_xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared_strings = _read_xlsx_shared_strings(archive) if "xl/sharedStrings.xml" in names else []
        sheet_names = sorted(
            [name for name in names if re.match(r"^xl/worksheets/sheet\d+\.xml$", name)],
            key=lambda item: int(re.search(r"sheet(\d+)\.xml$", item).group(1)),  # type: ignore[union-attr]
        )
        output: list[str] = []
        for sheet_idx, sheet_name in enumerate(sheet_names, start=1):
            root = ET.fromstring(archive.read(sheet_name))
            rows: list[str] = []
            for row in root.iter():
                if _local_name(row.tag) != "row":
                    continue
                cells = [_xlsx_cell_text(cell, shared_strings) for cell in list(row) if _local_name(cell.tag) == "c"]
                line = "\t".join(cell for cell in cells if cell != "")
                if line:
                    rows.append(line)
            if rows:
                output.append(f"[Sheet {sheet_idx}]\n" + "\n".join(rows))
        return "\n\n".join(output)


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root:
        if _local_name(item.tag) != "si":
            continue
        parts = [node.text or "" for node in item.iter() if _local_name(node.tag) == "t"]
        values.append("".join(parts))
    return values


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        parts = [node.text or "" for node in cell.iter() if _local_name(node.tag) == "t"]
        return "".join(parts).strip()

    value = ""
    for child in cell:
        if _local_name(child.tag) == "v":
            value = child.text or ""
            break
    if cell_type == "s":
        try:
            return shared_strings[int(value)].strip()
        except (ValueError, IndexError):
            return value.strip()
    return value.strip()


def _extract_pptx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            [name for name in archive.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", name)],
            key=lambda item: int(re.search(r"slide(\d+)\.xml$", item).group(1)),  # type: ignore[union-attr]
        )
        slides: list[str] = []
        for idx, slide_name in enumerate(slide_names, start=1):
            root = ET.fromstring(archive.read(slide_name))
            lines: list[str] = []
            for para in root.iter():
                if _local_name(para.tag) != "p":
                    continue
                line = _paragraph_text(para)
                if line:
                    lines.append(line)
            if lines:
                slides.append(f"[Slide {idx}]\n" + "\n".join(lines))
        return "\n\n".join(slides)


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on optional extra.
        raise RuntimeError("missing_dependency:pypdf") from exc

    reader = PdfReader(str(path))
    pages: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {idx}]\n{text.strip()}")
    return "\n\n".join(pages)


def extraction_summary(results: Iterable[DocumentExtraction]) -> str:
    """Return a compact JSON-ish string for logs and debugging."""

    payload = [
        {
            "name": item.name,
            "chars": len(item.text),
            "error": item.error,
            "truncated": item.truncated,
        }
        for item in results
    ]
    return json.dumps(payload, ensure_ascii=False)
