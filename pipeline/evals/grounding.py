"""Grounding / entailment check — the anti-hallucination ("anti-11x") layer.

1. Haiku extracts factual claims the email makes about the prospect.
2. Each claim is matched against the lead's chunks via the match_chunks RPC.
3. Haiku judges entailment vs the retrieved snippets.
An email fails grounding if ANY claim is unsupported (zero-hallucination policy).
"""

from __future__ import annotations

from pipeline import db, llm
from pipeline.budget import BudgetGuard
from pipeline.models import ClaimList, Entailment, GroundingClaim, GroundingResult
from pipeline.prompts import registry
from pipeline.researcher import embeddings


def _section(text: str, header: str) -> str:
    """Pull one `# header` block out of the combined grounding.md prompt."""
    blocks = text.split("# ")
    for b in blocks:
        if b.strip().startswith(header):
            return b.split("\n", 1)[1].strip()
    return text


def check_email(
    lead_id: str, subject: str, body: str, version: str = "v1", budget: BudgetGuard | None = None
) -> GroundingResult:
    prompt = registry.load("grounding", version).text
    extract_sys = _section(prompt, "claim_extraction")
    entail_sys = _section(prompt, "entailment")

    claims_obj, _ = llm.parse_writer(
        ClaimList, extract_sys, f"Subject: {subject}\n\n{body}", max_tokens=600, budget=budget
    )
    if not claims_obj.claims:
        return GroundingResult(passed=True, claims=[])

    results: list[GroundingClaim] = []
    for claim in claims_obj.claims:
        emb = embeddings.embed_query(claim)
        chunks = db.match_chunks(lead_id, emb, 3)
        if not chunks:
            # No retrievable evidence ⇒ unsupported by definition. Never ask the
            # judge to entail a claim against an empty snippet block — it can
            # rubber-stamp "supported", which would defeat the whole point.
            results.append(GroundingClaim(claim=claim, status="unsupported", best_source=None))
            continue
        snippets = "\n\n".join(f"(source: {c['url']})\n{c['content']}" for c in chunks)
        ent, _ = llm.parse_writer(
            Entailment,
            entail_sys,
            f"Claim: {claim}\n\nSnippets:\n{snippets}",
            max_tokens=200,
            budget=budget,
        )
        results.append(GroundingClaim(claim=claim, status=ent.status, best_source=chunks[0]["url"]))

    passed = not any(r.status == "unsupported" for r in results)
    return GroundingResult(passed=passed, claims=results)
