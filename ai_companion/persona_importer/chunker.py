from __future__ import annotations

from .schema import BookChunk, BookSection, CharacterTarget


def chunk_sections(
    sections: list[BookSection],
    *,
    chunk_chars: int = 6000,
    overlap_chars: int = 600,
) -> list[BookChunk]:
    if chunk_chars < 1000:
        raise ValueError("chunk_chars 不能小于 1000")
    if overlap_chars < 0:
        raise ValueError("overlap_chars 不能为负数")
    if overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars 必须小于 chunk_chars")

    chunks: list[BookChunk] = []
    for section in sections:
        text = section.text
        if not text:
            continue
        start = 0
        section_chunk_index = 0
        while start < len(text):
            end = min(len(text), start + chunk_chars)
            # Prefer ending at a paragraph boundary when it is close enough.
            if end < len(text):
                boundary = text.rfind("\n\n", start + int(chunk_chars * 0.65), end)
                if boundary > start:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = f"s{section.index:04d}_c{section_chunk_index:04d}"
                chunks.append(
                    BookChunk(
                        chunk_id=chunk_id,
                        section_index=section.index,
                        section_title=section.title,
                        text=chunk_text,
                        start_char=section.start_char + start,
                        end_char=section.start_char + end,
                    )
                )
                section_chunk_index += 1
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_chars)
    return chunks


def select_character_chunks(
    chunks: list[BookChunk],
    targets: list[CharacterTarget],
    *,
    include_neighbors: bool = True,
    skip_alias_filter: bool = False,
) -> list[tuple[BookChunk, list[CharacterTarget]]]:
    if skip_alias_filter:
        return [(chunk, targets) for chunk in chunks]

    selected_indices: set[int] = set()
    matches_by_index: dict[int, list[CharacterTarget]] = {}
    for index, chunk in enumerate(chunks):
        matched = [target for target in targets if _chunk_mentions_target(chunk.text, target)]
        if matched:
            selected_indices.add(index)
            matches_by_index[index] = matched
            if include_neighbors:
                if index > 0:
                    selected_indices.add(index - 1)
                if index + 1 < len(chunks):
                    selected_indices.add(index + 1)

    selected: list[tuple[BookChunk, list[CharacterTarget]]] = []
    for index in sorted(selected_indices):
        matched = matches_by_index.get(index)
        if matched is None:
            # Neighbor chunks may contain pronoun-only continuation. Ask about all
            # targets so the LLM can decide whether there is useful context.
            matched = targets
        selected.append((chunks[index], matched))
    return selected


def _chunk_mentions_target(text: str, target: CharacterTarget) -> bool:
    return any(name and name in text for name in target.all_names)
