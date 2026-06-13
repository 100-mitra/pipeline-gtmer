"""dead_letter node — terminal sink for any node that set state.error.

Persists stage='dead' + the reason and ends. Never raises, so the batch
orchestrator just moves on to the next lead.
"""

from __future__ import annotations

from typing import Any

from pipeline import db
from pipeline.graph.state import LeadState


def dead_letter_node(state: LeadState) -> dict[str, Any]:
    reason = state.error or "unknown"
    try:
        db.set_stage(state.lead_id, "dead", dead_reason=reason[:500])
    except Exception:  # noqa: BLE001 — even DB failure must not crash the batch
        pass
    return {"stage": "dead"}
