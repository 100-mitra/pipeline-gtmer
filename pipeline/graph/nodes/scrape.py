"""scrape_site node — fetch + chunk the prospect's pages (idempotent via cache/DB)."""

from __future__ import annotations

from typing import Any

from pipeline import db
from pipeline.graph.state import LeadState
from pipeline.researcher import chunker, scraper


def scrape_site_node(state: LeadState) -> dict[str, Any]:
    try:
        if db.has_chunks(state.lead_id):
            return {"pending_chunks": []}  # already embedded on a prior run
        pages = scraper.scrape_site(state.domain)
        if not pages:
            return {"error": f"scrape: no pages fetched for {state.domain}"}
        chunks = chunker.chunk_pages(pages)
        return {"pending_chunks": chunks}
    except Exception as e:  # noqa: BLE001 — becomes state, routes to dead_letter
        return {"error": f"scrape: {e!r}"}
