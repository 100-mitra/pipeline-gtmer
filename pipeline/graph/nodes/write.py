"""write_sequence node — 3-touch x 2-variant emails; advances lead to 'drafted'."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from pipeline import db
from pipeline.config import settings
from pipeline.graph.state import LeadState, cfg
from pipeline.models import Brief, Citation, JobSignal
from pipeline.writer import sequence


def write_sequence_node(state: LeadState, config: RunnableConfig) -> dict[str, Any]:
    budget, version = cfg(config)
    try:
        brief_row = db.get_brief(state.lead_id, f"brief:{version}")
        if not brief_row:
            return {"error": "write: brief missing"}
        active_pv = f"email_sequence:{version}"
        if db.has_emails(state.lead_id, active_pv):
            db.set_stage(state.lead_id, "drafted")
            return {"stage": "drafted", "prompt_version": active_pv}

        brief = Brief(
            content_md=brief_row["content_md"],
            citations=[Citation(**c) for c in (brief_row.get("citations") or [])],
        )
        job = JobSignal(title=state.job_title or "hiring SDRs", url=state.job_url)
        seq, pv_id = sequence.write_sequence(
            brief, job, state.company_name, version=version, budget=budget
        )
        db.save_emails(state.lead_id, seq.variants, pv_id, settings.writer_model)
        db.set_stage(state.lead_id, "drafted")
        n = sum(len(v.touches) for v in seq.variants)
        return {"n_emails": n, "prompt_version": pv_id, "stage": "drafted"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"write: {e!r}"}
