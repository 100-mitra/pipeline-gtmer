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

    # The verified hiring signal (the ATS job posting) is a first-class supported
    # fact — it's WHY this is a lead. The brief is a website scrape that won't
    # mention the posting, so without this the email's core personalization
    # ("X is hiring an SDR") would be falsely flagged as unsupported.
    lead = db.get_lead(lead_id)
    signal_src = ""
    if lead and lead.get("job_title") and lead.get("job_title") != "manual":
        signal_src = (
            "(source: verified public job posting)\n"
            f"{lead.get('company_name') or 'The company'} is currently hiring for the "
            f"role: {lead['job_title']}."
        )

    results: list[GroundingClaim] = []
    for claim in claims_obj.claims:
        emb = embeddings.embed_query(claim)
        chunks = db.match_chunks(lead_id, emb, 3)
        parts = ([signal_src] if signal_src else []) + [
            f"(source: {c['url']})\n{c['content']}" for c in chunks
        ]
        if not parts:
            # No evidence at all ⇒ unsupported. Never entail against an empty
            # snippet block — the judge can rubber-stamp "supported".
            results.append(GroundingClaim(claim=claim, status="unsupported", best_source=None))
            continue
        ent, _ = llm.parse_writer(
            Entailment,
            entail_sys,
            f"Claim: {claim}\n\nSnippets:\n" + "\n\n".join(parts),
            max_tokens=200,
            budget=budget,
        )
        best = chunks[0]["url"] if chunks else "verified job posting"
        results.append(GroundingClaim(claim=claim, status=ent.status, best_source=best))

    passed = not any(r.status == "unsupported" for r in results)
    return GroundingResult(passed=passed, claims=results)
