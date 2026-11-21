"""Heading-aware Markdown chunking.

Each ``##`` section becomes one chunk so that citations point at a meaningful unit. Sections
longer than ``max_chars`` are split on paragraph boundaries with ``overlap`` characters of
context carried into the next piece.
"""

import hashlib
import re

from app.rag.types import Chunk

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_HEADING = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.M)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, text[match.end() :]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces, current = [], ""
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars or not current:
            current = candidate
            continue
        pieces.append(current)
        current = f"{current[-overlap:]}\n\n{para}" if overlap else para
    if current:
        pieces.append(current)
    return pieces


def _chunk_id(source: str, section: str, text: str) -> str:
    return hashlib.sha1(f"{source}\x00{section}\x00{text}".encode()).hexdigest()[:16]


def chunk_markdown(
    text: str, source: str, max_chars: int = 1600, overlap: int = 240
) -> list[Chunk]:
    """Split one Markdown document into section chunks."""
    meta, body = parse_front_matter(text)
    doc_title = meta.get("title")
    matches = list(_HEADING.finditer(body))
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        level, heading = len(m.group(1)), m.group(2)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[m.end() : end].strip()
        if level == 1:
            doc_title = doc_title or heading
            if content:
                sections.append(("overview", content))
            continue
        if content:
            sections.append((heading, content))
    if not matches and body.strip():
        sections.append(("overview", body.strip()))

    chunks: list[Chunk] = []
    doc_title = doc_title or source
    for heading, content in sections:
        section = slugify(heading)
        title = doc_title if heading == "overview" else f"{doc_title} - {heading}"
        parts = _split_long(content, max_chars, overlap)
        for idx, part in enumerate(parts):
            sec = section if len(parts) == 1 else f"{section}-{idx + 1}"
            chunks.append(
                Chunk(
                    id=_chunk_id(source, sec, part),
                    source=source,
                    section=sec,
                    title=title,
                    text=part,
                )
            )
    return chunks
