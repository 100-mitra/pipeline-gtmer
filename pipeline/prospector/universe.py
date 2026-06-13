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


def is_india(text: str | None) -> bool:
    """True if a location string names an Indian city/region."""
    return bool(text) and any(tok in text.lower() for tok in INDIA_TOKENS)


def _is_b2b_saas(rec: dict) -> bool:
    tags = [t.lower() for t in rec.get("tags", [])]
    industry = str(rec.get("industry", "")).lower()
    return rec.get("status") != "Dead" and (
        any(t in SAAS_TAGS for t in tags) or "b2b" in industry or "saas" in industry
    )


def from_yc(limit: int = 200, india_only: bool = False) -> list[Company]:
    """Download the yc-oss all.json once and filter to B2B/SaaS client-side.

    India-HQ companies are returned FIRST (most pitch-relevant for GTMer), then
    global B2B SaaS to broaden the pool past the ~10% of Indian SaaS that use a
    supported ATS. Set `india_only=True` to restrict to India.
    """
    try:
        r = httpx.get(YC_ALL_URL, timeout=60)
        r.raise_for_status()
        records = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    india_list: list[Company] = []
    world_list: list[Company] = []
    for rec in records:
        if not _is_b2b_saas(rec):
            continue
        website = rec.get("website") or ""
        domain = website.replace("https://", "").replace("http://", "").strip("/").split("/")[0]
        if not domain:
            continue
        loc = rec.get("all_locations") or rec.get("location") or ""
        company = Company(name=rec.get("name", ""), domain=domain, hq_location=loc or None, source="yc-oss")
        if is_india(loc) or is_india(str(rec.get("regions", ""))):
            india_list.append(company)
        elif not india_only:
            world_list.append(company)
    if india_only:
        return india_list[:limit]
    # Interleave India (priority, but only ~140 exist and few use a supported ATS)
    # with the large global pool (high ATS yield), so BOTH get probed within the
    # limit. Ranking is handled separately by the India scoring boost — probe
    # order only affects which companies we discover, not how they're ordered.
    mixed: list[Company] = []
    i = j = 0
    while len(mixed) < limit and (i < len(india_list) or j < len(world_list)):
        if i < len(india_list):
            mixed.append(india_list[i])
            i += 1
        if j < len(world_list) and len(mixed) < limit:
            mixed.append(world_list[j])
            j += 1
    return mixed


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
