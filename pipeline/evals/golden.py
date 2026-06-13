"""Golden-set calibration — validate the judge before trusting its batch scores.

data/golden/golden_set.jsonl: one email per line with hand labels. We run the
judge over all of them and report exact-verdict agreement, Cohen's kappa, and
per-dimension MAE. Gate: kappa >= 0.6 before batch judge scores are trusted.

Each line:
{
  "id": "...", "brief_md": "...", "job_title": "...",
  "subject": "...", "body": "...",
  "human": {"personalization":4,"relevance_to_signal":5,"clarity":4,
            "cta_quality":4,"spam_risk":5,"verdict":"approve"}
}
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pipeline.budget import BudgetGuard
from pipeline.evals import judge
from pipeline.models import JudgeScore

GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "golden" / "golden_set.jsonl"
DIMS = ["personalization", "relevance_to_signal", "clarity", "cta_quality", "spam_risk"]


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two categorical raters (pure Python, no sklearn)."""
    n = len(a)
    if n == 0:
        return 0.0
    labels = set(a) | set(b)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def run(version: str = "v1") -> dict:
    rows = load_golden()
    if not rows:
        return {"error": "golden set is empty — author data/golden/golden_set.jsonl first"}

    budget = BudgetGuard()
    human_verdicts: list[str] = []
    judge_verdicts: list[str] = []
    dim_abs_err: dict[str, list[int]] = {d: [] for d in DIMS}

    for row in rows:
        score, _ = judge.judge_one(
            brief_md=row["brief_md"], job_title=row["job_title"],
            subject=row["subject"], body=row["body"], version=version, budget=budget,
        )
        human = row["human"]
        human_verdicts.append(human["verdict"])
        judge_verdicts.append(score.verdict)
        for d in DIMS:
            dim_abs_err[d].append(abs(getattr(score, d) - human[d]))

    n = len(rows)
    agreement = sum(1 for h, j in zip(human_verdicts, judge_verdicts) if h == j) / n
    kappa = cohens_kappa(human_verdicts, judge_verdicts)
    dim_mae = {d: round(sum(errs) / n, 3) for d, errs in dim_abs_err.items()}

    return {
        "n": n,
        "version": version,
        "verdict_agreement": round(agreement, 3),
        "cohens_kappa": round(kappa, 3),
        "dim_mae": dim_mae,
        "gate_pass": kappa >= 0.6,
        "est_cost_usd": round(budget.run_spent, 4),
    }
