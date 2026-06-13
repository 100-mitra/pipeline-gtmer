"""Supabase data access — all over HTTPS (REST + RPC).

We never open a direct Postgres connection: Supabase's direct host is IPv6-only,
which fails on typical IPv4 Windows networks. supabase-py's REST client and the
`match_chunks` RPC cover every read/write the pipeline needs.
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client


def _now() -> str:
    """ISO-8601 UTC timestamp. The Supabase REST API sends JSON string values
    literally, so a Postgres `now()` would arrive as the text 'now()' and fail
    the timestamptz cast — we must serialize an actual datetime."""
    return datetime.now(timezone.utc).isoformat()

from pipeline.config import settings
from pipeline.models import Brief, EmailVariant, JobSignal, QualifiedLead

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "sourced": {"researched", "dead"},
    "researched": {"drafted", "dead"},
    "drafted": {"scored", "dead"},
    "scored": {"approved", "dead"},
    "approved": set(),
    "dead": set(),
}


@functools.lru_cache(maxsize=1)
def client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ── runs ─────────────────────────────────────────────────────────────
def create_run(notes: str = "") -> str:
    row = client().table("runs").insert({"notes": notes}).execute().data[0]
    return row["id"]


def update_run(run_id: str, **fields: Any) -> None:
    client().table("runs").update(fields).eq("id", run_id).execute()


def lifetime_spend() -> float:
    rows = client().table("runs").select("est_cost_usd").execute().data
    return float(sum((r.get("est_cost_usd") or 0) for r in rows))


# ── leads ────────────────────────────────────────────────────────────
def upsert_lead(lead: QualifiedLead, run_id: str | None = None) -> str:
    """Insert or update by unique domain. Returns lead id."""
    payload = {
        "run_id": run_id,
        "company_name": lead.company.name,
        "domain": lead.company.domain,
        "ats_source": lead.job.ats_source,
        "ats_token": lead.job.ats_token,
        "job_title": lead.job.title,
        "job_url": lead.job.url,
        "job_posted_at": lead.job.posted_at,
        "signal_score": lead.signal_score,
        "signal_tier": lead.signal_tier,
        "hq_location": lead.company.hq_location,
    }
    row = (
        client()
        .table("leads")
        .upsert(payload, on_conflict="domain")
        .execute()
        .data[0]
    )
    return row["id"]


def manual_lead(company_name: str, domain: str, job_title: str = "", job_url: str | None = None) -> str:
    """Insert a hand-picked lead (used by `run-one`)."""
    lead = QualifiedLead(
        company={"name": company_name, "domain": domain},
        job=JobSignal(title=job_title or "manual", url=job_url, ats_source="manual"),
        signal_tier="warm",
    )
    return upsert_lead(lead)


def get_lead(lead_id: str) -> dict[str, Any] | None:
    rows = client().table("leads").select("*").eq("id", lead_id).execute().data
    return rows[0] if rows else None


def leads_by_stage(stage: str | None = None) -> list[dict[str, Any]]:
    q = client().table("leads").select("*").order("signal_score", desc=True)
    if stage:
        q = q.eq("stage", stage)
    return q.execute().data


def leads_behind(target_stage: str) -> list[dict[str, Any]]:
    """Leads not yet at `target_stage` and not dead — for resumable runs."""
    order = ["sourced", "researched", "drafted", "scored", "approved"]
    cut = order.index(target_stage)
    behind = order[:cut]
    return (
        client()
        .table("leads")
        .select("*")
        .in_("stage", behind)
        .order("signal_score", desc=True)
        .execute()
        .data
    )


def set_stage(lead_id: str, stage: str, dead_reason: str | None = None) -> None:
    fields: dict[str, Any] = {"stage": stage, "updated_at": _now()}
    if dead_reason is not None:
        fields["dead_reason"] = dead_reason
    client().table("leads").update(fields).eq("id", lead_id).execute()


def advance_stage(lead_id: str, to_stage: str) -> dict[str, Any]:
    """Validate + apply a stage transition (used by the dashboard advance button)."""
    lead = get_lead(lead_id)
    if not lead:
        raise ValueError("lead not found")
    current = lead["stage"]
    if to_stage not in LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"illegal transition {current} -> {to_stage}")
    set_stage(lead_id, to_stage)
    return get_lead(lead_id)  # type: ignore[return-value]


def enrich_contact(lead_id: str, **fields: Any) -> None:
    """linkedin_url / contact_name / contact_email — top-10 last-mile only."""
    client().table("leads").update(fields).eq("id", lead_id).execute()


# ── brief_chunks / briefs ────────────────────────────────────────────
def has_chunks(lead_id: str) -> bool:
    rows = (
        client().table("brief_chunks").select("id").eq("lead_id", lead_id).limit(1).execute().data
    )
    return bool(rows)


def save_chunks(lead_id: str, chunks: list[dict[str, Any]]) -> None:
    """chunks: [{url, chunk_index, content, embedding}]"""
    rows = [{"lead_id": lead_id, **c} for c in chunks]
    client().table("brief_chunks").insert(rows).execute()


def match_chunks(lead_id: str, query_embedding: list[float], match_count: int = 6) -> list[dict[str, Any]]:
    return (
        client()
        .rpc(
            "match_chunks",
            {
                "p_lead_id": lead_id,
                "p_query_embedding": query_embedding,
                "p_match_count": match_count,
            },
        )
        .execute()
        .data
    )


def get_brief(lead_id: str, prompt_version: str | None = None) -> dict[str, Any] | None:
    q = client().table("briefs").select("*").eq("lead_id", lead_id)
    if prompt_version:
        q = q.eq("prompt_version", prompt_version)
    rows = q.limit(1).execute().data
    return rows[0] if rows else None


def save_brief(
    lead_id: str, brief: Brief, prompt_version: str, model: str, in_tok: int, out_tok: int
) -> str:
    payload = {
        "lead_id": lead_id,
        "content_md": brief.content_md,
        "citations": [c.model_dump() for c in brief.citations],
        "prompt_version": prompt_version,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    }
    row = client().table("briefs").upsert(payload, on_conflict="lead_id,prompt_version").execute().data[0]
    return row["id"]


# ── emails ───────────────────────────────────────────────────────────
def has_emails(lead_id: str, prompt_version: str) -> bool:
    rows = (
        client()
        .table("emails")
        .select("id")
        .eq("lead_id", lead_id)
        .eq("prompt_version", prompt_version)
        .limit(1)
        .execute()
        .data
    )
    return bool(rows)


def save_emails(lead_id: str, variants: list[EmailVariant], prompt_version: str, model: str) -> list[str]:
    rows = []
    for v in variants:
        for t in v.touches:
            rows.append(
                {
                    "lead_id": lead_id,
                    "variant": v.variant,
                    "touch": t.touch,
                    "subject": t.subject,
                    "body": t.body,
                    "prompt_version": prompt_version,
                    "model": model,
                }
            )
    res = (
        client()
        .table("emails")
        .upsert(rows, on_conflict="lead_id,variant,touch,prompt_version")
        .execute()
        .data
    )
    return [r["id"] for r in res]


def emails_for_lead(lead_id: str) -> list[dict[str, Any]]:
    return (
        client()
        .table("emails")
        .select("*")
        .eq("lead_id", lead_id)
        .order("variant")
        .order("touch")
        .execute()
        .data
    )


# ── evals ────────────────────────────────────────────────────────────
def save_eval(
    *,
    lead_id: str | None,
    email_id: str | None,
    kind: str,
    passed: bool | None = None,
    scores: dict[str, Any] | None = None,
    overall: float | None = None,
    feedback: str | None = None,
    judge_model: str | None = None,
    prompt_version: str | None = None,
) -> str:
    payload = {
        "lead_id": lead_id,
        "email_id": email_id,
        "kind": kind,
        "passed": passed,
        "scores": scores,
        "overall": overall,
        "feedback": feedback,
        "judge_model": judge_model,
        "prompt_version": prompt_version,
    }
    return client().table("evals").insert(payload).execute().data[0]["id"]


def evals_for_lead(lead_id: str) -> list[dict[str, Any]]:
    return client().table("evals").select("*").eq("lead_id", lead_id).execute().data


def evals_for_email(email_id: str) -> list[dict[str, Any]]:
    return client().table("evals").select("*").eq("email_id", email_id).execute().data


# ── prompt_versions ──────────────────────────────────────────────────
def register_prompt(pv_id: str, task: str, version: str, sha256: str, active: bool = True) -> None:
    client().table("prompt_versions").upsert(
        {"id": pv_id, "task": task, "version": version, "sha256": sha256, "active": active},
        on_conflict="id",
    ).execute()
