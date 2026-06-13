"""Qualification — is a job posting an SDR/BDR buying signal, and how strong?

Pure functions, table-tested. A company hiring SDR/BDR capacity is investing in
outbound — exactly what GTMer automates — so a live posting is the intent signal.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# Title patterns. Tiered: a true SDR/BDR role is a stronger signal than a broad
# "sales" req. SDET / software roles must NOT match (the classic false positive).
STRONG_RE = re.compile(
    r"\b(sdr|bdr|sales development (rep|representative)?|business development rep(resentative)?|"
    r"account development rep(resentative)?|inside sales)\b",
    re.IGNORECASE,
)
WEAK_RE = re.compile(
    r"\b(sales executive|sales associate|lead generation|demand generation|gtm|"
    r"revenue (associate|operations))\b",
    re.IGNORECASE,
)
# Guard against software/engineering false positives ("SDET", "SDR engineer" rare).
EXCLUDE_RE = re.compile(r"\b(sdet|software|engineer|developer|qa|test)\b", re.IGNORECASE)


def title_matches(title: str) -> str | None:
    """Return 'strong' | 'weak' | None for a job title."""
    if EXCLUDE_RE.search(title) and not STRONG_RE.search(title):
        return None
    if STRONG_RE.search(title):
        return "strong"
    if WEAK_RE.search(title):
        return "weak"
    return None


def _days_old(posted_at: str | None) -> int | None:
    if not posted_at:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(posted_at, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except ValueError:
            continue
    return None


def score_signal(title: str, posted_at: str | None) -> tuple[int, str, str]:
    """Return (score 0-100, tier hot|warm|cold, evidence)."""
    match = title_matches(title)
    if match is None:
        return 0, "cold", "no SDR/BDR signal in title"

    base = 70 if match == "strong" else 50
    days = _days_old(posted_at)
    recency = 0
    if days is not None:
        if days <= 14:
            recency = 25
        elif days <= 45:
            recency = 15
        elif days <= 90:
            recency = 5
    score = min(100, base + recency)
    tier = "hot" if score >= 80 else "warm" if score >= 50 else "cold"
    age = f"{days}d old" if days is not None else "age unknown"
    evidence = f"{match} title match ('{title}'), {age}"
    return score, tier, evidence
