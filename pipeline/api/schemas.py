"""Response DTOs for the read API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LeadCard(BaseModel):
    id: str
    company_name: str
    domain: str
    stage: str
    job_title: str | None = None
    signal_score: int | None = None
    signal_tier: str | None = None


class KanbanColumn(BaseModel):
    stage: str
    leads: list[LeadCard]


class LeadDetail(BaseModel):
    lead: dict[str, Any]
    brief: dict[str, Any] | None
    emails: list[dict[str, Any]]
    evals: list[dict[str, Any]]


class AdvanceRequest(BaseModel):
    to_stage: str


class EvalsSummary(BaseModel):
    leads_by_stage: dict[str, int]
    heuristic_pass_rate: float | None
    grounding_pass_rate: float | None
    avg_judge_overall: float | None
    judge_kappa: float | None
    total_cost_usd: float
