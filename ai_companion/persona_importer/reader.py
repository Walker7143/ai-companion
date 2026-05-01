from __future__ import annotations

import html
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from .schema import BookDocument, BookSection


TEXT_ENCODING_CANDIDATES = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "gbk",
    "big5",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in {"p", "br", "div", "section", "article", "h1", "h2", "h3", "li"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() in {"p", "div", "section", "article", "h1", "h2", "h3", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str):
        text = html.unescape(data)
        if text.strip():
            self._parts.append(text)

    def text(self) -> str:
        return normalize_text("".join(self._parts))


def load_book(path: Path, *, encoding: str | None = None) -> BookDocument:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"找不到书籍文件: {path}")

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        text, used_encoding = _read_text_file(path, encoding=encoding)
        return _document_from_text(path, text, suffix.lstrip("."), encoding=used_encoding)
    if suffix in {".html", ".htm", ".xhtml"}:
        raw, used_encoding = _read_text_file(path, encoding=encoding)
        text = _html_to_text(raw)
        return _document_from_text(path, text, suffix.lstrip("."), encoding=used_encoding)
    if suffix == ".epub":
        text = _read_epub(path)
        return _document_from_text(path, text, "epub", encoding="epub-html")
    if suffix == ".pdf":
        text = _read_pdf(path)
        return _document_from_text(path, text, "pdf", encoding="pdf-extract")

    raise ValueError(f"暂不支持的书籍格式: {suffix or path.name}")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _read_text_file(path: Path, *, encoding: str | None = None) -> tuple[str, str]:
    candidates = [encoding] if encoding else list(TEXT_ENCODING_CANDIDATES)
    errors: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return path.read_text(encoding=candidate), candidate
        except UnicodeDecodeError as exc:
            errors.append(f"{candidate}: {exc}")
        except LookupError as exc:
            raise ValueError(f"未知文本编码: {candidate}") from exc

    # Last-resort decode keeps the import usable and makes the chosen fallback
    # visible in manifest.json for review.
    if encoding:
        detail = "; ".join(errors[-3:]) if errors else "no decoder details"
        raise ValueError(f"无法按指定编码 {encoding} 读取文件: {path}。{detail}")
    raw = path.read_bytes()
    if not raw:
        return "", "binary-empty"
    return raw.decode("gb18030", errors="replace"), "gb18030-replace"


def _document_from_text(path: Path, text: str, source_format: str, *, encoding: str | None = None) -> BookDocument:
    text = normalize_text(text)
    if not text:
        raise ValueError(f"书籍文件没有可读取文本: {path}")
    sections = split_sections(text)
    return BookDocument(
        path=path,
        title=path.stem,
        sections=sections,
        source_format=source_format,
        encoding=encoding,
    )


_SECTION_LINE_RE = re.compile(
    r"^\s*(?:"
    r"#{1,3}\s+.+|"
    r"第[一二三四五六七八九十百千万零〇两\d]+[章节回部卷].*|"
    r"(?:Chapter|CHAPTER)\s+\d+.*"
    r")\s*$"
)


def split_sections(text: str) -> list[BookSection]:
    lines = text.splitlines()
    markers: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) <= 80 and _SECTION_LINE_RE.match(stripped):
            markers.append((offset, stripped.lstrip("#").strip()))
        offset += len(line) + 1

    if not markers:
        return [BookSection(index=0, title="全文", text=text, start_char=0)]

    sections: list[BookSection] = []
    for idx, (start, title) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            sections.append(
                BookSection(
                    index=len(sections),
                    title=title,
                    text=section_text,
                    start_char=start,
                )
            )
    return sections or [BookSection(index=0, title="全文", text=text, start_char=0)]


def _html_to_text(raw: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    return parser.text()


def _read_epub(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        ordered = _epub_spine_items(archive, names)
        if not ordered:
            ordered = sorted(
                name for name in names
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            )
        parts: list[str] = []
        for name in ordered:
            try:
                raw = archive.read(name).decode("utf-8", errors="ignore")
            except KeyError:
                continue
            text = _html_to_text(raw)
            if text:
                parts.append(text)
        return "\n\n".join(parts)


def _epub_spine_items(archive: zipfile.ZipFile, names: set[str]) -> list[str]:
    try:
        container = archive.read("META-INF/container.xml")
    except KeyError:
        return []
    try:
        root = ElementTree.fromstring(container)
    except ElementTree.ParseError:
        return []

    opf_name = ""
    for elem in root.iter():
        if elem.tag.endswith("rootfile"):
            opf_name = elem.attrib.get("full-path", "")
            break
    if not opf_name or opf_name not in names:
        return []

    try:
        opf_root = ElementTree.fromstring(archive.read(opf_name))
    except ElementTree.ParseError:
        return []

    manifest: dict[str, str] = {}
    spine_ids: list[str] = []
    for elem in opf_root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "item":
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            if item_id and href:
                manifest[item_id] = href
        elif tag == "itemref":
            ref = elem.attrib.get("idref")
            if ref:
                spine_ids.append(ref)

    base = Path(opf_name).parent
    ordered: list[str] = []
    for item_id in spine_ids:
        href = manifest.get(item_id)
        if not href:
            continue
        candidate = str((base / href).as_posix()).lstrip("./")
        if candidate in names:
            ordered.append(candidate)
    return ordered


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise ValueError("读取 PDF 需要安装可选依赖 pypdf，或先转换为 txt/epub。") from exc

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts)
