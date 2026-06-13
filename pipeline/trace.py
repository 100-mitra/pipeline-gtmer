"""Langfuse v4 tracing — optional, never blocks a run.

Returns a LangGraph CallbackHandler when keys are set, else None. Short-lived CLI
scripts MUST call `flush()` before exit or buffered traces are dropped.
"""

from __future__ import annotations

import contextlib
from typing import Any

from pipeline.config import settings


def handler() -> Any | None:
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()  # zero-arg in v4; creds come from env / singleton
    except Exception:  # noqa: BLE001
        return None


@contextlib.contextmanager
def attributes(**attrs: Any):
    """Tag the enclosed traces (lead_id, run_id, prompt_version)."""
    if not settings.langfuse_enabled:
        yield
        return
    try:
        from langfuse import propagate_attributes

        with propagate_attributes(metadata={k: str(v) for k, v in attrs.items()}):
            yield
    except Exception:  # noqa: BLE001
        yield


def flush() -> None:
    if not settings.langfuse_enabled:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:  # noqa: BLE001
        pass
