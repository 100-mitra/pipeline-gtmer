"""Orchestration — prospect the universe, then drive the per-lead graph.

The graph is per-lead; this module owns the cross-lead concerns: the shared
BudgetGuard, the run record, Langfuse tagging, and the "never crash the batch"
guarantee (dead-letter handles node errors; BudgetExceeded aborts cleanly).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from pipeline import db
from pipeline.budget import BudgetExceeded, BudgetGuard
from pipeline.config import settings
from pipeline.graph.build import build_graph
from pipeline.graph.state import LeadState
from pipeline.models import Company, JobSignal, QualifiedLead
from pipeline.prompts import registry
from pipeline.prospector import ats, qualify, universe
from pipeline import trace

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; gtmer-prospect/0.1)"}
CAREERS_PATHS = ["/careers", "/jobs", "/company/careers", ""]


# ── Prospecting ──────────────────────────────────────────────────────
def _resolve_token(company: Company) -> tuple[str, str] | None:
    urls = []
    if company.careers_url:
        urls.append(company.careers_url)
    base = f"https://{company.domain.rstrip('/')}"
    urls += [base + p for p in CAREERS_PATHS]
    for url in urls:
        try:
            r = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
            if r.status_code == 200:
                found = ats.discover_token(r.text)
                if found:
                    return found
        except httpx.HTTPError:
            continue
    return None


def _best_signal(company: Company) -> QualifiedLead | None:
    found = _resolve_token(company)
    if not found:
        return None
    source, token = found
    best: QualifiedLead | None = None
    for job in ats.fetch_jobs(source, token):
        if qualify.title_matches(job.title) is None:
            continue
        score, tier, evidence = qualify.score_signal(job.title, job.posted_at)
        if best is None or score > best.signal_score:
            best = QualifiedLead(
                company=company, job=job, signal_score=score, signal_tier=tier, evidence=evidence
            )
    return best


def prospect(limit: int = 100, include_yc: bool = True, run_id: str | None = None) -> dict:
    companies = universe.build_universe(limit=limit, include_yc=include_yc)
    sourced = 0
    for c in companies:
        lead = _best_signal(c)
        if lead is None:
            continue
        db.upsert_lead(lead, run_id=run_id)
        sourced += 1
    return {"probed": len(companies), "sourced": sourced}


# ── Pipeline (graph) orchestration ───────────────────────────────────
def _state_from_row(row: dict, run_id: str | None) -> LeadState:
    return LeadState(
        lead_id=row["id"],
        run_id=run_id,
        company_name=row["company_name"],
        domain=row["domain"],
        job_title=row.get("job_title") or "",
        job_url=row.get("job_url"),
    )


def _invoke(graph, state: LeadState, budget: BudgetGuard, version: str) -> LeadState:
    cbs = [h for h in (trace.handler(),) if h]
    config = {"configurable": {"budget": budget, "version": version}}
    if cbs:
        config["callbacks"] = cbs
    with trace.attributes(lead_id=state.lead_id, run_id=state.run_id or "", version=version):
        result = graph.invoke(state, config=config)
    return LeadState(**result) if isinstance(result, dict) else result


def run_pipeline(limit: int | None = None, version: str = "v1", target: str = "scored") -> dict:
    registry.ensure_prompts(version)  # fail fast on a bad --version, before any run record / API call
    run_id = db.create_run(notes=f"target={target} version={version}")
    registry.register_all(version)  # record active prompt versions for the audit trail
    budget = BudgetGuard(lifetime_spent=db.lifetime_spend())
    graph = build_graph()

    rows = db.leads_behind(target)
    if limit:
        rows = rows[:limit]

    completed = dead = 0
    status = "completed"
    try:
        for row in rows:
            state = _state_from_row(row, run_id)
            out = _invoke(graph, state, budget, version)
            if out.stage == "dead":
                dead += 1
            elif out.stage in ("scored", "drafted", "researched"):
                completed += 1
    except BudgetExceeded as e:
        status = "aborted_budget"
        db.set_stage(row["id"], "dead", dead_reason=f"budget_abort: {e}")  # type: ignore[possibly-undefined]
        dead += 1
    finally:
        db.update_run(
            run_id,
            status=status,
            finished_at=datetime.now(timezone.utc).isoformat(),
            leads_attempted=len(rows),
            leads_completed=completed,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            est_cost_usd=round(budget.run_spent, 4),
        )
        trace.flush()

    return {
        "run_id": run_id,
        "status": status,
        "attempted": len(rows),
        "completed": completed,
        "dead": dead,
        "est_cost_usd": round(budget.run_spent, 4),
    }


def run_one(domain: str, company: str, job_title: str = "", job_url: str | None = None, version: str = "v1") -> dict:
    registry.ensure_prompts(version)
    registry.register_all(version)
    lead_id = db.manual_lead(company, domain, job_title, job_url)
    budget = BudgetGuard(lifetime_spent=db.lifetime_spend())
    graph = build_graph()
    state = LeadState(lead_id=lead_id, company_name=company, domain=domain, job_title=job_title, job_url=job_url)
    out = _invoke(graph, state, budget, version)
    trace.flush()
    return {
        "lead_id": lead_id,
        "stage": out.stage,
        "error": out.error,
        "n_citations": out.n_citations,
        "n_emails": out.n_emails,
        "eval_summary": out.eval_summary,
        "est_cost_usd": round(budget.run_spent, 4),
    }
