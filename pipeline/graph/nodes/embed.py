"""embed_chunks node — Voyage-embed the pending chunks and store them."""

from __future__ import annotations

from typing import Any

from pipeline import db
from pipeline.graph.state import LeadState
from pipeline.researcher import embeddings


def embed_chunks_node(state: LeadState) -> dict[str, Any]:
    try:
        if db.has_chunks(state.lead_id):
            return {}  # idempotent: embeddings already exist
        if not state.pending_chunks:
            return {"error": "embed: no chunks to embed"}
        vectors = embeddings.embed_documents([c["content"] for c in state.pending_chunks])
        rows = [{**c, "embedding": v} for c, v in zip(state.pending_chunks, vectors)]
        db.save_chunks(state.lead_id, rows)
        return {"chunk_count": len(rows), "pending_chunks": []}
    except Exception as e:  # noqa: BLE001
        return {"error": f"embed: {e!r}"}
