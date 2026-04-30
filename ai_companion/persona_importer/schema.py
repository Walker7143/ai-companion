from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


CORE_PERSONA_FILES = (
    "profile.json",
    "backstory.json",
    "values.json",
    "speaking_style.json",
    "conversation_style_rules.json",
)


@dataclass(slots=True)
class CharacterTarget:
    """A character to extract from the source book."""

    name: str
    bot_id: str
    aliases: list[str] = field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        names: list[str] = []
        for value in [self.name, *self.aliases]:
            value = str(value or "").strip()
            if value and value not in names:
                names.append(value)
        return names

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bot_id": self.bot_id,
            "aliases": self.aliases,
            "all_names": self.all_names,
        }


@dataclass(slots=True)
class BookSection:
    index: int
    title: str
    text: str
    start_char: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "chars": len(self.text),
            "start_char": self.start_char,
        }


@dataclass(slots=True)
class BookDocument:
    path: Path
    title: str
    sections: list[BookSection]
    source_format: str

    @property
    def char_count(self) -> int:
        return sum(len(section.text) for section in self.sections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "title": self.title,
            "source_format": self.source_format,
            "sections": len(self.sections),
            "chars": self.char_count,
        }


@dataclass(slots=True)
class BookChunk:
    chunk_id: str
    section_index: int
    section_title: str
    text: str
    start_char: int
    end_char: int

    def to_prompt_header(self) -> str:
        return (
            f"chunk_id: {self.chunk_id}\n"
            f"section: {self.section_title or f'第{self.section_index + 1}节'}\n"
            f"char_range: {self.start_char}-{self.end_char}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "section_index": self.section_index,
            "section_title": self.section_title,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "chars": len(self.text),
        }


@dataclass(slots=True)
class ImportOptions:
    book_path: Path
    characters: list[CharacterTarget]
    output_dir: Path
    chunk_chars: int = 6000
    overlap_chars: int = 600
    merge_batch_chars: int = 24000
    max_concurrency: int = 1
    requests_per_minute: float = 0
    retry_attempts: int = 3
    retry_base_delay_seconds: float = 2.0
    resume: bool = True
    max_chunks: int | None = None
    include_neighbor_chunks: bool = True
    skip_alias_filter: bool = False
    plan_only: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def parse_character_spec(spec: str) -> CharacterTarget:
    """Parse CLI character specs.

    Supported forms:
      - "林黛玉"
      - "林黛玉=黛玉,林妹妹"
      - "lin_daiyu:林黛玉=黛玉,林妹妹"
    """
    raw = str(spec or "").strip()
    if not raw:
        raise ValueError("角色不能为空")

    bot_id = ""
    body = raw
    if ":" in raw:
        maybe_id, maybe_body = raw.split(":", 1)
        if re.fullmatch(r"[A-Za-z0-9_-]+", maybe_id.strip()) and maybe_body.strip():
            bot_id = maybe_id.strip()
            body = maybe_body.strip()

    if "=" in body:
        name, alias_text = body.split("=", 1)
        aliases = [
            item.strip()
            for item in re.split(r"[,，|、/]", alias_text)
            if item.strip()
        ]
    else:
        name = body
        aliases = []

    name = name.strip()
    if not name:
        raise ValueError(f"角色规格无效: {spec}")
    if not bot_id:
        bot_id = make_bot_id(name)
    aliases = [alias for alias in aliases if alias != name]
    return CharacterTarget(name=name, bot_id=bot_id, aliases=aliases)


def make_bot_id(name: str) -> str:
    """Create a stable bot id without adding transliteration dependencies."""
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_").lower()
    if base:
        return base[:48]
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"role_{digest}"
