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

HUNTER_FINDER = "https://api.hunter.io/v2/email-finder"
HUNTER_DOMAIN = "https://api.hunter.io/v2/domain-search"
# Prefer a sales/leadership contact for a cold pitch about outbound.
_PREF_DEPT = {"sales", "executive", "management", "marketing"}
_PREF_POS = ("sales", "founder", "ceo", "chief", "head", "growth", "revenue", "gtm", "vp")


def _avg_judge(lead_id: str) -> float:
    rows = [e for e in db.evals_for_lead(lead_id) if e["kind"] == "judge" and e.get("overall")]
    return sum(e["overall"] for e in rows) / len(rows) if rows else 0.0


def top_approved(n: int = 10) -> list[dict]:
    leads = db.leads_by_stage("approved")
    leads.sort(key=lambda l: _avg_judge(l["id"]), reverse=True)
    return leads[:n]


def _finder(domain: str, full_name: str) -> dict | None:
    try:
        r = httpx.get(HUNTER_FINDER, params={"domain": domain, "full_name": full_name,
                                             "api_key": settings.hunter_api_key}, timeout=20)
        r.raise_for_status()
        d = r.json().get("data", {})
        if not d.get("email"):
            return None
        return {"email": d["email"], "score": d.get("score"),
                "verified": (d.get("verification") or {}).get("status"),
                "name": full_name, "position": d.get("position")}
    except (httpx.HTTPError, ValueError):
        return None


def _domain_best(domain: str) -> dict | None:
    """Pick the most pitch-relevant contact at a domain (sales/leadership, highest confidence)."""
    try:
        # Hunter's free plan caps domain-search at 10 results (limit>10 -> 400).
        r = httpx.get(HUNTER_DOMAIN, params={"domain": domain, "limit": 10,
                                             "api_key": settings.hunter_api_key}, timeout=20)
        r.raise_for_status()
        emails = (r.json().get("data") or {}).get("emails", [])
    except (httpx.HTTPError, ValueError):
        return None
    if not emails:
        return None

    def rank(e: dict) -> tuple:
        dept = (e.get("department") or "").lower()
        pos = (e.get("position") or "").lower()
        pref = 2 if (dept in _PREF_DEPT or any(k in pos for k in _PREF_POS)) else (
            1 if e.get("type") == "personal" else 0)
        return (pref, e.get("confidence") or 0)

    best = max(emails, key=rank)
    name = " ".join(filter(None, [best.get("first_name"), best.get("last_name")])) or None
    return {"email": best["value"], "score": best.get("confidence"), "verified": None,
            "name": name, "position": best.get("position")}


def find_email(domain: str, full_name: str | None = None) -> dict | None:
    if not settings.hunter_api_key:
        return None
    if full_name:  # most accurate when we already know the person
        res = _finder(domain, full_name)
        if res:
            return res
    return _domain_best(domain)  # else find the best sales/leadership contact at the domain


def enrich_top10() -> dict:
    enriched = []
    for lead in top_approved(10):
        result = find_email(lead["domain"], lead.get("contact_name"))
        if result:
            fields = {"contact_email": result["email"]}
            if result.get("name"):
                fields["contact_name"] = result["name"]
            db.enrich_contact(lead["id"], **fields)
            enriched.append({"company": lead["company_name"], **result})
    return {"enriched": len(enriched), "leads": enriched}
