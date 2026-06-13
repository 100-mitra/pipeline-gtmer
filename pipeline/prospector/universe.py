"""Company universe — the set of companies to probe for SDR/BDR signals.

Primary source = a hand-curated CSV of Indian B2B SaaS companies (data/companies_in.csv),
because it is the most reliable India-targeted seed. Supplementary = the yc-oss
static JSON mirror of YC companies (no region endpoint → filter India client-side
on the per-company `regions` / `all_locations` fields).
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx

from pipeline.models import Company

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CSV_PATH = DATA_DIR / "companies_in.csv"
YC_ALL_URL = "https://yc-oss.github.io/api/companies/all.json"

INDIA_TOKENS = ("india", "bangalore", "bengaluru", "mumbai", "delhi", "gurgaon",
                "gurugram", "pune", "hyderabad", "chennai", "noida", "kolkata")
SAAS_TAGS = ("saas", "b2b", "b2b-software", "developer-tools", "sales", "marketing",
             "fintech", "productivity", "analytics", "ai")


def from_csv(path: Path = CSV_PATH) -> list[Company]:
    if not path.exists():
        return []
    out: list[Company] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("domain"):
                continue
            out.append(
                Company(
                    name=row["name"].strip(),
                    domain=row["domain"].strip(),
                    careers_url=(row.get("careers_url") or "").strip() or None,
                    hq_location=(row.get("hq_location") or "").strip() or None,
                    source="csv",
                )
            )
    return out


def _is_india_saas(rec: dict) -> bool:
    blob = " ".join(
        str(rec.get(k, "")) for k in ("regions", "all_locations", "location")
    ).lower()
    if not any(tok in blob for tok in INDIA_TOKENS):
        return False
    tags = [t.lower() for t in rec.get("tags", [])]
    industry = str(rec.get("industry", "")).lower()
    return rec.get("status") != "Dead" and (
        any(t in SAAS_TAGS for t in tags) or "b2b" in industry or "saas" in industry
    )


def from_yc(limit: int = 200) -> list[Company]:
    """Download the yc-oss all.json once and filter to India B2B/SaaS client-side."""
    try:
        r = httpx.get(YC_ALL_URL, timeout=60)
        r.raise_for_status()
        records = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    out: list[Company] = []
    for rec in records:
        if not _is_india_saas(rec):
            continue
        website = rec.get("website") or ""
        domain = website.replace("https://", "").replace("http://", "").strip("/").split("/")[0]
        if not domain:
            continue
        out.append(
            Company(
                name=rec.get("name", ""),
                domain=domain,
                hq_location=(rec.get("all_locations") or rec.get("location") or None),
                source="yc-oss",
            )
        )
        if len(out) >= limit:
            break
    return out


def build_universe(limit: int = 200, include_yc: bool = True) -> list[Company]:
    """CSV first (primary), then YC supplements, de-duped by domain."""
    seen: set[str] = set()
    universe: list[Company] = []
    for c in from_csv() + (from_yc(limit) if include_yc else []):
        if c.domain in seen:
            continue
        seen.add(c.domain)
        universe.append(c)
        if len(universe) >= limit:
            break
    return universe
