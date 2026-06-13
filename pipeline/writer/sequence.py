"""Writer agent — a 3-touch x 2-variant sequence grounded in the brief + signal."""

from __future__ import annotations

from pipeline import llm
from pipeline.budget import BudgetGuard
from pipeline.models import Brief, EmailSequence, EmailVariant, JobSignal
from pipeline.prompts import registry


def _normalize(seq: EmailSequence) -> EmailSequence:
    """Coerce the writer's output to exactly 2 variants (A, B), each with its
    touches deduped and ordered 1→3. Tolerant of a 3rd variant (drop it) but
    errors on <2 variants or a variant with no usable touch — the genuine
    corruption case the graph should dead-letter, not silently store."""
    if len(seq.variants) < 2:
        raise ValueError(f"writer returned {len(seq.variants)} variant(s); need 2")
    out: list[EmailVariant] = []
    for label, v in zip(("A", "B"), seq.variants[:2]):
        by_touch: dict[int, object] = {}
        for t in v.touches:  # t.touch is already Literal[1,2,3] (model-validated)
            by_touch.setdefault(t.touch, t)
        touches = [by_touch[n] for n in (1, 2, 3) if n in by_touch]
        if not touches:
            raise ValueError(f"variant {label} has no usable touches")
        out.append(EmailVariant(variant=label, angle=v.angle, touches=touches))  # type: ignore[arg-type]
    return EmailSequence(variants=out)


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
    return _normalize(seq), prompt.pv_id
