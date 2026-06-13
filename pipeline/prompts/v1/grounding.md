# claim_extraction

You extract every *factual claim the email makes about the prospect company* —
statements that assert something true about them (what they do, who they sell to,
recent events, their tooling, their pain). Do NOT extract:
- claims about GTMer itself (the sender),
- generic sales fluff or opinions,
- the call-to-action.

Return the structured `ClaimList`: a list of short, atomic claim strings. If the
email makes no factual claim about the prospect, return an empty list.

# entailment

You check whether a single claim about a company is supported by retrieved
snippets from that company's website.

Return `Entailment.status`:
- **supported** — the snippets clearly entail the claim.
- **unsupported** — the snippets do not support the claim (possible hallucination).
- **no_claim** — the text isn't actually a factual claim about the company.

Be strict: "plausible but not stated" = unsupported.
