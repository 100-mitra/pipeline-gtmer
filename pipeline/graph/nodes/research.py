"""research_brief node — RAG-grounded cited brief; advances lead to 'researched'."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from pipeline import db
from pipeline.config import settings
from pipeline.graph.state import LeadState, cfg
from pipeline.researcher import brief as brief_mod


def research_brief_node(state: LeadState, config: RunnableConfig) -> dict[str, Any]:
    budget, version = cfg(config)
    try:
        existing = db.get_brief(state.lead_id, f"brief:{version}")
        if existing:
            db.set_stage(state.lead_id, "researched")
            return {
                "brief_md": existing["content_md"],
                "n_citations": len(existing.get("citations") or []),
                "prompt_version": existing["prompt_version"],
                "stage": "researched",
            }
        brief, pv_id, in_tok, out_tok = brief_mod.build_brief(state.lead_id, version, budget)
        db.save_brief(state.lead_id, brief, pv_id, settings.writer_model, in_tok, out_tok)
        db.set_stage(state.lead_id, "researched")
        return {
            "brief_md": brief.content_md,
            "n_citations": len(brief.citations),
            "prompt_version": pv_id,
            "stage": "researched",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"research: {e!r}"}
