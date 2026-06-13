"""Last-mile contact enrichment for the top-10 leads only.

Hunter.io free tier = 50 credits/month (1 credit = email found). We enrich at
most the top 10 *approved* leads by average judge score, so this stays well under
budget. LinkedIn URLs are added manually (no ToS-safe automated source) via
`db.enrich_contact`.
"""

from __future__ import annotations

import httpx

from pipeline import db
from pipeline.config import settings

HUNTER_URL = "https://api.hunter.io/v2/email-finder"


def _avg_judge(lead_id: str) -> float:
    evals = db.evals_for_email  # noqa: F841  (kept for symmetry)
    rows = [e for e in db.evals_for_lead(lead_id) if e["kind"] == "judge" and e.get("overall")]
    return sum(e["overall"] for e in rows) / len(rows) if rows else 0.0


def top_approved(n: int = 10) -> list[dict]:
    leads = db.leads_by_stage("approved")
    leads.sort(key=lambda l: _avg_judge(l["id"]), reverse=True)
    return leads[:n]


def find_email(domain: str, full_name: str | None = None) -> dict | None:
    if not settings.hunter_api_key:
        return None
    params = {"domain": domain, "api_key": settings.hunter_api_key}
    if full_name:
        params["full_name"] = full_name
    try:
        r = httpx.get(HUNTER_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", {})
        if not data.get("email"):
            return None
        return {"email": data["email"], "score": data.get("score"), "verified": data.get("verification", {}).get("status")}
    except (httpx.HTTPError, ValueError):
        return None


def enrich_top10() -> dict:
    enriched = []
    for lead in top_approved(10):
        # contact_name is set manually beforehand if known; Hunter can find by domain alone.
        result = find_email(lead["domain"], lead.get("contact_name"))
        if result:
            db.enrich_contact(lead["id"], contact_email=result["email"])
            enriched.append({"company": lead["company_name"], **result})
    return {"enriched": len(enriched), "leads": enriched}
