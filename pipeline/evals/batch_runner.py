"""Run-level Batch-API judge pass (50% off) over all drafted leads.

The per-lead graph uses the sync judge (correct for run-one). For the full
50-lead run, this batches every email that cleared heuristics + grounding into a
single Batch API job, halving the judge cost. It complements the graph rather
than restructuring it: run `gtmer run` first (to scored via sync) OR run the
graph only to 'drafted' and finish judging here.

Usage: gtmer judge-batch
"""

from __future__ import annotations

import time

from pipeline import db, llm
from pipeline.config import settings
from pipeline.evals import grounding, heuristics, judge
from pipeline.budget import BudgetGuard
from pipeline.prompts import registry


def _eligible_emails(lead: dict, budget: BudgetGuard, version: str = "v1") -> list[dict]:
    """Emails for a lead that pass heuristics + grounding (so worth judging)."""
    brief = db.get_brief(lead["id"], f"brief:{version}")
    out: list[dict] = []
    for em in db.emails_for_lead(lead["id"]):
        h = heuristics.check_touch(
            touch=em["touch"], subject=em["subject"], body=em["body"],
            company_name=lead["company_name"], job_title=lead.get("job_title") or "",
        )
        db.save_eval(lead_id=lead["id"], email_id=em["id"], kind="heuristic",
                     passed=h.passed, scores={"checks": h.checks, "detail": h.detail})
        if not h.passed:
            continue
        g = grounding.check_email(lead["id"], em["subject"], em["body"], version=version, budget=budget)
        db.save_eval(lead_id=lead["id"], email_id=em["id"], kind="grounding",
                     passed=g.passed, scores={"claims": [c.model_dump() for c in g.claims]})
        if g.passed:
            out.append(em | {"_brief_md": brief["content_md"] if brief else "",
                             "_job_title": lead.get("job_title") or "", "_lead_id": lead["id"]})
    return out


def run(version: str = "v1", poll_seconds: int = 30) -> dict:
    registry.ensure_prompts(version)
    budget = BudgetGuard(lifetime_spent=db.lifetime_spend())
    leads = [l for l in db.leads_by_stage() if l["stage"] in ("drafted", "scored")]

    requests: list[dict] = []
    index: dict[str, dict] = {}
    for lead in leads:
        for em in _eligible_emails(lead, budget, version):
            cid = em["id"]
            index[cid] = em
            requests.append(
                judge.build_batch_request(
                    cid, brief_md=em["_brief_md"], job_title=em["_job_title"],
                    subject=em["subject"], body=em["body"], version=version,
                )
            )

    if not requests:
        return {"judged": 0, "note": "no emails passed heuristics + grounding"}

    batch_id = llm.batch_create(requests)
    while not llm.batch_ready(batch_id):
        time.sleep(poll_seconds)

    judged = 0
    for result in llm.batch_results(batch_id):
        u = judge.result_usage(result)
        if u:
            budget.record(u)  # count the batch judge cost (50% discount applied)
        score = judge.parse_batch_result(result)
        em = index.get(result.custom_id)
        if not em:
            continue
        if score is None:
            db.save_eval(lead_id=em["_lead_id"], email_id=em["id"], kind="judge",
                         passed=None, feedback="batch result error/refusal",
                         judge_model=settings.judge_model)
            continue
        db.save_eval(lead_id=em["_lead_id"], email_id=em["id"], kind="judge",
                     passed=score.verdict != "reject", scores=score.model_dump(),
                     overall=score.overall, feedback=score.rationale,
                     judge_model=settings.judge_model, prompt_version=f"judge_rubric:{version}")
        judged += 1

    # Advance any judged lead to 'scored'.
    for lead in leads:
        if lead["stage"] == "drafted" and db.evals_for_lead(lead["id"]):
            db.set_stage(lead["id"], "scored")

    return {"batch_id": batch_id, "requests": len(requests), "judged": judged,
            "est_cost_usd": round(budget.run_spent, 4)}
