"""Split scraped pages into ~500-token chunks that keep their source URL."""

from __future__ import annotations

from pipeline.models import ScrapedPage

# ~4 chars/token heuristic → ~500 tokens ≈ 2000 chars. Small overlap preserves
# cross-boundary sentences.
CHUNK_CHARS = 2000
OVERLAP_CHARS = 200


def chunk_page(page: ScrapedPage) -> list[tuple[str, str]]:
    """Return [(url, content), ...] for one page."""
    text = page.text
    out: list[tuple[str, str]] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_CHARS
        out.append((page.url, text[start:end].strip()))
        if end >= len(text):
            break
        start = end - OVERLAP_CHARS
    return [(u, c) for u, c in out if c]


def chunk_pages(pages: list[ScrapedPage]) -> list[dict]:
    """Return rows ready for the brief_chunks table (sans embedding)."""
    rows: list[dict] = []
    idx = 0
    for page in pages:
        for url, content in chunk_page(page):
            rows.append({"url": url, "chunk_index": idx, "content": content})
            idx += 1
    return rows
