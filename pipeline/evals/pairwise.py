"""Randomized pairwise prompt-version comparison.

Absolute 1-5 scores drift; pairwise preferences are stabler. To decide whether a
new writer-prompt version is better, we regenerate touch-1 for a fixed set of
leads under both versions and ask Sonnet which is better — with A/B presentation
order RANDOMIZED per pair (LLM judges have measurable position bias).

Promotion rule: the new version must win >= 65% of decided (non-tie) pairs.
"""

from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel

from pipeline import db, llm
from pipeline.budget import BudgetGuard
from pipeline.config import settings
from pipeline.models import Brief, Citation, JobSignal
from pipeline.writer import sequence

PAIRWISE_SYSTEM = (
    "You compare two cold-email openers written to the same prospect. Pick the one "
    "that is more personalized, more credibly tied to the prospect's SDR/BDR hiring "
    "signal, clearer, and lower spam-risk. If genuinely equal, answer 'tie'. Judge "
    "on merit; position is irrelevant."
)


class PairwiseVerdict(BaseModel):
    winner: Literal["A", "B", "tie"]
    reason: str


def _opener(brief: Brief, job: JobSignal, company: str, version: str, budget: BudgetGuard) -> str:
    seq, _ = sequence.write_sequence(brief, job, company, version=version, budget=budget)
    return seq.variants[0].touches[0].body


def _brief_from_row(row: dict) -> Brief:
    cites = [Citation(**c) for c in (row.get("citations") or [])]
    return Brief(content_md=row["content_md"], citations=cites)


def run(a_version: str, b_version: str, n: int = 20, seed: int = 7) -> dict:
    """Compare writer prompt `a_version` (incumbent) vs `b_version` (challenger)."""
    rng = random.Random(seed)
    budget = BudgetGuard()

    leads = [l for l in db.leads_by_stage() if l["stage"] in ("drafted", "scored", "approved")][:n]
    wins = {"A": 0, "B": 0, "tie": 0}
    pairs: list[dict] = []

    for lead in leads:
        brief_row = db.get_brief(lead["id"])
        if not brief_row:
            continue
        brief = _brief_from_row(brief_row)
        job = JobSignal(title=lead.get("job_title") or "hiring SDRs", url=lead.get("job_url"))
        company = lead["company_name"]

        a_text = _opener(brief, job, company, a_version, budget)
        b_text = _opener(brief, job, company, b_version, budget)

        # Randomize presentation order to neutralize position bias.
        swap = rng.random() < 0.5
        left, right = (b_text, a_text) if swap else (a_text, b_text)
        user = f"Prospect: {company}\nSignal: {job.title}\n\nEmail A:\n{left}\n\nEmail B:\n{right}"
        verdict, _ = llm.parse_judge(PairwiseVerdict, PAIRWISE_SYSTEM, user, max_tokens=300, budget=budget)

        # Map the displayed winner back to the real version.
        if verdict.winner == "tie":
            real = "tie"
        elif (verdict.winner == "A") != swap:  # A shown == a_version unless swapped
            real = "A"
        else:
            real = "B"
        wins[real] += 1
        pairs.append({"lead": company, "winner": real, "reason": verdict.reason})

    decided = wins["A"] + wins["B"]
    b_winrate = (wins["B"] / decided) if decided else 0.0
    return {
        "a_version": a_version,
        "b_version": b_version,
        "judge_model": settings.judge_model,
        "wins": wins,
        "b_winrate": round(b_winrate, 3),
        "promote_b": b_winrate >= 0.65,
        "pairs": pairs,
        "est_cost_usd": round(budget.run_spent, 4),
    }
