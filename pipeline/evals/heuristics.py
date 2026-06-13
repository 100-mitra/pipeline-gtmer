"""Free, deterministic checks. Run FIRST — a failure skips the paid eval stages.

Pure functions, table-tested in tests/test_heuristics.py.
"""

from __future__ import annotations

import re

from pipeline.models import HeuristicResult

SPAM_WORDS = [
    "guarantee", "guaranteed", "free!!", "act now", "limited time", "risk-free",
    "100%", "buy now", "click here", "cheap", "discount", "% off", "winner",
    "no obligation", "amazing offer", "best price",
]
BANNED_PHRASES = [
    "i hope this finds you well", "quick question", "circling back",
    "just following up", "touching base", "synergy", "as an ai",
]
PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|\[name\]|\[company\]|<company>|<name>|x{3,}", re.IGNORECASE)

WORD_BOUNDS = {1: (25, 95), 2: (10, 55), 3: (10, 65)}  # per-touch word count (subject excluded)


def _words(text: str) -> int:
    return len(text.split())


def check_touch(*, touch: int, subject: str, body: str, company_name: str, job_title: str) -> HeuristicResult:
    low_body = body.lower()
    low_subj = subject.lower()
    lo, hi = WORD_BOUNDS.get(touch, (10, 95))
    wc = _words(body)

    checks: dict[str, bool] = {}
    detail: dict[str, str] = {}

    checks["body_length"] = lo <= wc <= hi
    if not checks["body_length"]:
        detail["body_length"] = f"{wc} words (want {lo}-{hi})"

    checks["subject_length"] = 1 <= _words(subject) <= 8 and subject != subject.upper()

    # Fake "Re:"/"Fwd:" subjects on a first-contact email are a deceptive pattern
    # (and a deliverability/ethics red flag). The judge catches them; so should
    # the free layer. Observed on the first run ("Re: Your SDR hire").
    checks["no_fake_thread"] = re.match(r"\s*(re|fwd?|fw)\s*:", subject, re.IGNORECASE) is None
    if not checks["no_fake_thread"]:
        detail["no_fake_thread"] = "fake reply/forward subject"

    checks["no_spam_words"] = not any(w in low_body or w in low_subj for w in SPAM_WORDS)
    if not checks["no_spam_words"]:
        hit = next(w for w in SPAM_WORDS if w in low_body or w in low_subj)
        detail["no_spam_words"] = f"contains '{hit}'"

    checks["no_banned_phrases"] = not any(p in low_body for p in BANNED_PHRASES)
    if not checks["no_banned_phrases"]:
        hit = next(p for p in BANNED_PHRASES if p in low_body)
        detail["no_banned_phrases"] = f"contains '{hit}'"

    checks["no_placeholders"] = PLACEHOLDER_RE.search(body) is None and PLACEHOLDER_RE.search(subject) is None
    checks["single_cta"] = body.count("?") <= 1

    # Touch 1 must reference the hiring signal AND the company by name. Accept both
    # the title's own words and how reps actually phrase the role (SDR/BDR/outbound).
    if touch == 1:
        title_tokens = {t for t in re.split(r"\W+", job_title.lower()) if len(t) > 3}
        signal_terms = title_tokens | {
            "sdr", "bdr", "outbound", "sales development", "business development", "inside sales",
        }
        checks["references_signal"] = any(t in low_body for t in signal_terms)
        checks["personalized"] = company_name.lower().split()[0] in low_body if company_name else True

    passed = all(checks.values())
    return HeuristicResult(passed=passed, checks=checks, detail=detail)
