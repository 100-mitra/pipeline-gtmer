"""run_evals node — cost-ordered cascade per email; advances lead to 'scored'.

heuristics (free) → grounding (cheap) → judge (Sonnet). A heuristic failure skips
the paid stages for that email. Each stage writes an `evals` row. The sync judge
is used here (correct for run-one); the 50-lead run swaps in the Batch API judge
at the orchestrator level for the 50% discount.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from pipeline import db
from pipeline.config import settings
from pipeline.evals import grounding, heuristics, judge
from pipeline.graph.state import LeadState, cfg


def run_evals_node(state: LeadState, config: RunnableConfig) -> dict[str, Any]:
    budget, version = cfg(config)
    try:
        emails = db.emails_for_lead(state.lead_id)
        if not emails:
            return {"error": "evals: no emails to score"}
        brief_row = db.get_brief(state.lead_id)
        brief_md = brief_row["content_md"] if brief_row else ""

        n_pass_h = n_pass_g = n_judged = 0
        overalls: list[float] = []

        for em in emails:
            h = heuristics.check_touch(
                touch=em["touch"], subject=em["subject"], body=em["body"],
                company_name=state.company_name, job_title=state.job_title,
            )
            db.save_eval(
                lead_id=state.lead_id, email_id=em["id"], kind="heuristic",
                passed=h.passed, scores={"checks": h.checks, "detail": h.detail},
            )
            if not h.passed:
                continue
            n_pass_h += 1

            g = grounding.check_email(state.lead_id, em["subject"], em["body"], version, budget)
            db.save_eval(
                lead_id=state.lead_id, email_id=em["id"], kind="grounding",
                passed=g.passed, scores={"claims": [c.model_dump() for c in g.claims]},
            )
            if not g.passed:
                continue
            n_pass_g += 1

            score, pv_id = judge.judge_one(
                brief_md=brief_md, job_title=state.job_title,
                subject=em["subject"], body=em["body"], version=version, budget=budget,
            )
            db.save_eval(
                lead_id=state.lead_id, email_id=em["id"], kind="judge",
                passed=score.verdict != "reject", scores=score.model_dump(),
                overall=score.overall, feedback=score.rationale,
                judge_model=settings.judge_model, prompt_version=pv_id,
            )
            n_judged += 1
            overalls.append(score.overall)

        summary = {
            "emails": len(emails),
            "heuristic_pass": n_pass_h,
            "grounding_pass": n_pass_g,
            "judged": n_judged,
            "avg_overall": round(sum(overalls) / len(overalls), 2) if overalls else None,
        }
        db.set_stage(state.lead_id, "scored")
        return {"eval_summary": summary, "stage": "scored"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"evals: {e!r}"}
