"""Generate a retrieval-grounded research brief.

This is the demonstrable RAG step: we retrieve the most relevant chunks per
research question via the `match_chunks` RPC, then prompt Haiku to write a cited
brief from ONLY those snippets (not raw context-stuffing).
"""

from __future__ import annotations

from pipeline import db, llm
from pipeline.budget import BudgetGuard
from pipeline.models import Brief
from pipeline.prompts import registry
from pipeline.researcher import embeddings

# Questions that drive retrieval — each pulls the chunks most useful for a brief.
RESEARCH_QUESTIONS = [
    "What does the company do and what product do they sell?",
    "Who are their target customers and ICP?",
    "Recent news: funding, product launches, hiring, or expansion.",
    "How do they sell and what are their go-to-market or outbound challenges?",
]


def _retrieve(lead_id: str, per_q: int = 3) -> list[dict]:
    seen: set[str] = set()
    chunks: list[dict] = []
    for q in RESEARCH_QUESTIONS:
        emb = embeddings.embed_query(q)
        for row in db.match_chunks(lead_id, emb, per_q):
            if row["id"] not in seen:
                seen.add(row["id"])
                chunks.append(row)
    return chunks


def build_brief(lead_id: str, version: str = "v1", budget: BudgetGuard | None = None) -> tuple[Brief, str, int, int]:
    """Return (brief, prompt_version_id, in_tokens, out_tokens)."""
    prompt = registry.load("brief", version)
    chunks = _retrieve(lead_id)
    if not chunks:
        raise RuntimeError("no retrievable chunks for lead (embed step likely empty)")

    numbered = "\n\n".join(
        f"[{i + 1}] (source: {c['url']})\n{c['content']}" for i, c in enumerate(chunks)
    )
    user = f"Retrieved snippets:\n\n{numbered}\n\nWrite the brief now."
    brief, usage = llm.parse_writer(Brief, prompt.text, user, max_tokens=1200, budget=budget)
    return brief, prompt.pv_id, usage.input_tokens, usage.output_tokens
