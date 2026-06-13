"""Per-lead graph state + helpers to read run config (budget, prompt version)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from pipeline.budget import BudgetGuard


class LeadState(BaseModel):
    lead_id: str
    run_id: str | None = None
    company_name: str
    domain: str
    job_title: str = ""
    job_url: str | None = None

    pending_chunks: list[dict[str, Any]] = Field(default_factory=list)  # transient: url/index/content
    chunk_count: int = 0
    brief_md: str | None = None
    n_citations: int = 0
    n_emails: int = 0
    prompt_version: str | None = None
    eval_summary: dict[str, Any] | None = None

    stage: str = "sourced"
    error: str | None = None


def cfg(config: Any) -> tuple[BudgetGuard, str]:
    """Extract (budget, prompt_version) from a LangGraph RunnableConfig."""
    conf = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    budget = conf.get("budget") or BudgetGuard()
    version = conf.get("version", "v1")
    return budget, version
