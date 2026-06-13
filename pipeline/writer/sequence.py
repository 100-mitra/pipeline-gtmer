"""Writer agent — a 3-touch x 2-variant sequence grounded in the brief + signal."""

from __future__ import annotations

from pipeline import llm
from pipeline.budget import BudgetGuard
from pipeline.models import Brief, EmailSequence, JobSignal
from pipeline.prompts import registry


def write_sequence(
    brief: Brief,
    job: JobSignal,
    company_name: str,
    version: str = "v1",
    budget: BudgetGuard | None = None,
) -> tuple[EmailSequence, str]:
    """Return (sequence, prompt_version_id)."""
    prompt = registry.load("email_sequence", version)
    citations = "\n".join(f"[{c.n}] {c.url}" for c in brief.citations)
    user = (
        f"Prospect company: {company_name}\n"
        f"Hiring signal (the hook): {job.title}"
        + (f" — {job.url}" if job.url else "")
        + "\n\n"
        f"Research brief:\n{brief.content_md}\n\n"
        f"Citations:\n{citations}\n\n"
        "Write the two-variant, three-touch sequence now."
    )
    seq, _ = llm.parse_writer(EmailSequence, prompt.text, user, max_tokens=2000, budget=budget)
    return seq, prompt.pv_id
