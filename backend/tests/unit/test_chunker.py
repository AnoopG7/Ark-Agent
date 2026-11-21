from app.core.config import get_settings
from app.rag.chunker import chunk_markdown, parse_front_matter, slugify
from app.rag.ingest import load_chunks

DOC = """---
title: Test SOP
version: 1
---

# Test SOP

## Daily allowance
Plan 3 litres per person.

## Quality and handling
Sealed jerrycans only.
"""


def test_front_matter_parsed() -> None:
    meta, body = parse_front_matter(DOC)
    assert meta["title"] == "Test SOP"
    assert body.lstrip().startswith("# Test SOP")


def test_one_chunk_per_section_with_citation() -> None:
    chunks = chunk_markdown(DOC, source="sop-test.md")
    assert [c.citation for c in chunks] == [
        "sop-test.md#daily-allowance",
        "sop-test.md#quality-and-handling",
    ]
    assert chunks[0].title == "Test SOP - Daily allowance"
    assert chunks[0].text == "Plan 3 litres per person."


def test_ids_are_deterministic_and_content_sensitive() -> None:
    a = chunk_markdown(DOC, source="sop-test.md")
    b = chunk_markdown(DOC, source="sop-test.md")
    c = chunk_markdown(DOC.replace("3 litres", "4 litres"), source="sop-test.md")
    assert [x.id for x in a] == [x.id for x in b]
    assert a[0].id != c[0].id and a[1].id == c[1].id


def test_long_section_split_with_overlap() -> None:
    paras = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    chunks = chunk_markdown(f"# T\n\n## Big\n{paras}", source="t.md", max_chars=800, overlap=100)
    assert len(chunks) > 1
    assert all(len(c.text) <= 800 + 100 + 400 for c in chunks)
    assert chunks[0].section == "big-1" and chunks[1].section == "big-2"
    assert chunks[0].text[-100:] in chunks[1].text


def test_slugify() -> None:
    assert slugify("Quality & Handling!") == "quality-handling"


def test_knowledge_base_loads() -> None:
    chunks = load_chunks(get_settings().knowledge_dir)
    sources = {c.source for c in chunks}
    assert len(sources) >= 8
    assert "sop-water-supply.md#daily-allowance" in {c.citation for c in chunks}
    assert len({c.id for c in chunks}) == len(chunks)
