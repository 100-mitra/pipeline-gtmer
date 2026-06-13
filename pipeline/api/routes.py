"""Read-mostly API. One mutation (advance). The /for-gtmer page is slug-gated."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from pipeline import db
from pipeline.api.schemas import (
    AdvanceRequest,
    EvalsSummary,
    KanbanColumn,
    LeadCard,
    LeadDetail,
)
from pipeline.config import settings

router = APIRouter()
STAGES = ["sourced", "researched", "drafted", "scored", "approved"]


def _redact_contact(lead: dict) -> dict:
    """Mask the contact email on the PUBLIC surface (e.g. k****@company.com). Full
    contact data is served only by the slug-gated /for-gtmer deliverable — sloppy
    handling of scraped personal data is the last thing to show a founder in this space."""
    out = dict(lead)
    email = out.get("contact_email")
    if email and "@" in email:
        local, _, domain = email.partition("@")
        out["contact_email"] = f"{local[0]}****@{domain}"
    return out


@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@router.get("/api/leads")
def list_leads(stage: str | None = None) -> list[KanbanColumn]:
    rows = db.leads_by_stage(stage)
    by_stage: dict[str, list[LeadCard]] = defaultdict(list)
    for r in rows:
        by_stage[r["stage"]].append(
            LeadCard(
                id=r["id"], company_name=r["company_name"], domain=r["domain"],
                stage=r["stage"], job_title=r.get("job_title"),
                signal_score=r.get("signal_score"), signal_tier=r.get("signal_tier"),
            )
        )
    cols = [stage] if stage else STAGES
    return [KanbanColumn(stage=s, leads=by_stage.get(s, [])) for s in cols]


@router.get("/api/leads/{lead_id}")
def lead_detail(lead_id: str) -> LeadDetail:
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    return LeadDetail(
        lead=_redact_contact(lead),  # public surface — email masked; full only on /for-gtmer
        brief=db.get_brief(lead_id),
        emails=db.emails_for_lead(lead_id),
        evals=db.evals_for_lead(lead_id),
    )


@router.post("/api/leads/{lead_id}/advance")
def advance(lead_id: str, body: AdvanceRequest) -> dict:
    # Promotion to 'approved' requires every email to clear heuristics + grounding
    # and not be judge-rejected. Human still clicks the button (human-in-the-loop).
    if body.to_stage == "approved" and not _approval_eligible(lead_id):
        raise HTTPException(409, "lead has unresolved heuristic/grounding/judge failures")
    try:
        return db.advance_stage(lead_id, body.to_stage)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


def _approval_eligible(lead_id: str) -> bool:
    evals = db.evals_for_lead(lead_id)
    by_email: dict[str, dict[str, dict]] = defaultdict(dict)
    for e in evals:
        if e.get("email_id"):
            by_email[e["email_id"]][e["kind"]] = e
    if not by_email:
        return False
    for kinds in by_email.values():
        if "judge" not in kinds:
            continue  # email that failed an earlier gate; ignore, others may pass
        if not kinds.get("heuristic", {}).get("passed"):
            return False
        if not kinds.get("grounding", {}).get("passed"):
            return False
        scores = kinds["judge"].get("scores") or {}
        if scores.get("verdict") == "reject":
            return False
    return any("judge" in k for k in by_email.values())


@router.get("/api/evals/summary")
def evals_summary() -> EvalsSummary:
    counts = {s: len(db.leads_by_stage(s)) for s in STAGES + ["dead"]}
    cli = db.client()
    evals = cli.table("evals").select("kind,passed,overall").execute().data

    def rate(kind: str) -> float | None:
        rows = [e for e in evals if e["kind"] == kind and e["passed"] is not None]
        return round(sum(1 for e in rows if e["passed"]) / len(rows), 3) if rows else None

    overalls = [e["overall"] for e in evals if e["kind"] == "judge" and e["overall"] is not None]
    runs = cli.table("runs").select("est_cost_usd").execute().data
    return EvalsSummary(
        leads_by_stage=counts,
        heuristic_pass_rate=rate("heuristic"),
        grounding_pass_rate=rate("grounding"),
        avg_judge_overall=round(sum(overalls) / len(overalls), 2) if overalls else None,
        judge_kappa=None,  # populated from the golden-set run; surfaced in the dashboard text
        total_cost_usd=round(sum((r.get("est_cost_usd") or 0) for r in runs), 4),
    )


@router.get("/api/for-gtmer/{slug}")
def for_gtmer(slug: str) -> dict:
    if not settings.for_gtmer_slug or slug != settings.for_gtmer_slug:
        raise HTTPException(404, "not found")
    leads = db.leads_by_stage("approved")
    payload = []
    for lead in leads:
        payload.append(
            {
                "lead": lead,
                "brief": db.get_brief(lead["id"]),
                "emails": db.emails_for_lead(lead["id"]),
                "evals": db.evals_for_lead(lead["id"]),
            }
        )
    return {"count": len(payload), "leads": payload}
