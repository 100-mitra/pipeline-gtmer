"""Domain models — Pydantic v2. Shared across prospector, researcher, writer, evals.

Structured-output note: Anthropic's structured-outputs schema rejects numeric
`minimum`/`maximum`. Any field an LLM fills via `messages.parse` that needs a
bounded integer uses `Literal[...]` (compiles to JSON-Schema `enum`, supported),
never `Field(ge=..., le=...)`.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Stage = Literal["sourced", "researched", "drafted", "scored", "approved", "dead"]
SignalTier = Literal["hot", "warm", "cold"]
AtsSource = Literal["greenhouse", "lever", "ashby", "manual"]
Score = Literal[1, 2, 3, 4, 5]
Touch = Literal[1, 2, 3]  # email-sequence touch number — DB CHECK enforces 1..3


# ── Prospector ───────────────────────────────────────────────────────
class Company(BaseModel):
    """A candidate company before qualification."""

    name: str
    domain: str
    careers_url: str | None = None
    hq_location: str | None = None
    source: str = "csv"  # csv | yc-oss


class JobSignal(BaseModel):
    """A live SDR/BDR posting = a buying signal for an AI-SDR tool."""

    title: str
    url: str | None = None
    posted_at: str | None = None  # ISO date if the ATS exposes it
    ats_source: AtsSource = "manual"
    ats_token: str | None = None


class QualifiedLead(BaseModel):
    company: Company
    job: JobSignal
    signal_score: int = Field(default=0, description="0-100 ICP/intent/reachability")
    signal_tier: SignalTier = "cold"
    evidence: str = ""  # why this score — stored alongside it


# ── Researcher ───────────────────────────────────────────────────────
class ScrapedPage(BaseModel):
    url: str
    text: str
    fetched_via: Literal["httpx", "firecrawl", "cache"] = "httpx"


class Citation(BaseModel):
    n: int
    url: str
    quote: str = ""


class Brief(BaseModel):
    """Retrieval-grounded research brief. Claims in `content_md` carry [n] markers."""

    content_md: str
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("citations")
    @classmethod
    def _markers_have_citations(cls, v: list[Citation], info) -> list[Citation]:
        """Reject a brief that cites [n] markers but ships zero citations — an
        uncited brief makes the grounding eval (the anti-hallucination layer) a
        no-op and lets the writer make unsupported claims."""
        content = info.data.get("content_md", "")
        if re.search(r"\[\d+\]", content) and not v:
            raise ValueError("content_md has [n] markers but citations list is empty")
        return v


# ── Writer ───────────────────────────────────────────────────────────
class EmailTouch(BaseModel):
    touch: Touch  # 1 | 2 | 3 — matches the DB CHECK (touch between 1 and 3)
    subject: str
    body: str


class EmailVariant(BaseModel):
    variant: Literal["A", "B"]
    angle: str = ""  # one-line description of the angle, for the eval A/B story
    touches: list[EmailTouch]


class EmailSequence(BaseModel):
    """Writer output: 2 variants × 3 touches, grounded in the brief + job signal."""

    variants: list[EmailVariant]

    @field_validator("variants")
    @classmethod
    def _exactly_two_by_three(cls, v: list[EmailVariant]) -> list[EmailVariant]:
        """Enforce exactly 2 variants (A and B), each with touches {1,2,3}. A
        malformed sequence (e.g. 1 variant) would otherwise save silently and the
        A/B eval would only ever score one side."""
        if len(v) != 2:
            raise ValueError(f"expected exactly 2 variants, got {len(v)}")
        if {var.variant for var in v} != {"A", "B"}:
            raise ValueError("variants must be labelled A and B")
        for var in v:
            if sorted(t.touch for t in var.touches) != [1, 2, 3]:
                raise ValueError(f"variant {var.variant} must have touches 1,2,3")
        return v


# ── Evals ────────────────────────────────────────────────────────────
class HeuristicResult(BaseModel):
    passed: bool
    checks: dict[str, bool]
    detail: dict[str, str] = Field(default_factory=dict)


class GroundingClaim(BaseModel):
    claim: str
    status: Literal["supported", "unsupported", "no_claim"]
    best_source: str | None = None


class GroundingResult(BaseModel):
    passed: bool  # fails if ANY claim is "unsupported"
    claims: list[GroundingClaim] = Field(default_factory=list)


class JudgeScore(BaseModel):
    """Sonnet rubric output. All dims are Literal (schema rejects ge/le)."""

    personalization: Score
    relevance_to_signal: Score
    clarity: Score
    cta_quality: Score
    spam_risk: Score  # 5 = lowest risk
    verdict: Literal["approve", "revise", "reject"]
    rationale: str

    @property
    def overall(self) -> float:
        return round(
            (
                self.personalization
                + self.relevance_to_signal
                + self.clarity
                + self.cta_quality
                + self.spam_risk
            )
            / 5,
            2,
        )


class ClaimList(BaseModel):
    """Structured-output container for the grounding claim-extraction call."""

    claims: list[str]


class Entailment(BaseModel):
    status: Literal["supported", "unsupported", "no_claim"]


# ── Usage / cost ─────────────────────────────────────────────────────
class Usage(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    batched: bool = False
