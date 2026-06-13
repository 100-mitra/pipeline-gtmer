"""Public ATS job-board adapters — the only ToS-safe, no-auth, structured source.

Greenhouse / Lever / Ashby all expose a company's open roles as public JSON with
no authentication (vendor-sanctioned). We (1) discover a company's board token
from its careers page, then (2) fetch + normalize its postings.

Excluded by design (documented in the README): Wellfound (DataDome 403s),
Naukri (edge-blocks non-browsers), Cutshort (ToS bans automated collection),
Google SERP scraping (ToS).
"""

from __future__ import annotations

import re

import httpx

from pipeline.models import JobSignal

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; gtmer-prospect/0.1)"}

# Board-token patterns found on careers pages / embed scripts.
TOKEN_PATTERNS = {
    "greenhouse": re.compile(r"boards\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)", re.I),
    "lever": re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)", re.I),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_-]+)", re.I),
}


def discover_token(careers_html: str) -> tuple[str, str] | None:
    """Return (ats_source, token) found in a careers page's HTML, or None."""
    for source, pat in TOKEN_PATTERNS.items():
        m = pat.search(careers_html)
        if m:
            return source, m.group(1)
    return None


def _get_json(url: str) -> dict | list | None:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        return None


def fetch_greenhouse(token: str) -> list[JobSignal]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    jobs = (data or {}).get("jobs", []) if isinstance(data, dict) else []
    return [
        JobSignal(
            title=j.get("title", ""),
            url=j.get("absolute_url"),
            posted_at=j.get("updated_at") or j.get("first_published"),
            ats_source="greenhouse",
            ats_token=token,
        )
        for j in jobs
    ]


def fetch_lever(token: str) -> list[JobSignal]:
    data = _get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    jobs = data if isinstance(data, list) else []
    out: list[JobSignal] = []
    for j in jobs:
        created = j.get("createdAt")
        posted = None
        if isinstance(created, (int, float)):  # Lever returns epoch millis
            from datetime import datetime, timezone

            posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append(
            JobSignal(
                title=j.get("text", ""),
                url=j.get("hostedUrl"),
                posted_at=posted,
                ats_source="lever",
                ats_token=token,
            )
        )
    return out


def fetch_ashby(token: str) -> list[JobSignal]:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    jobs = (data or {}).get("jobs", []) if isinstance(data, dict) else []
    return [
        JobSignal(
            title=j.get("title", ""),
            url=j.get("jobUrl"),
            posted_at=j.get("publishedDate"),
            ats_source="ashby",
            ats_token=token,
        )
        for j in jobs
    ]


_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def fetch_jobs(source: str, token: str) -> list[JobSignal]:
    fetcher = _FETCHERS.get(source)
    return fetcher(token) if fetcher else []
