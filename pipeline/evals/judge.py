"""LLM-as-judge — Sonnet scores each email against the rubric.

Two paths:
  - `judge_one` (sync, .parse) for the dev loop and the golden set.
  - `judge_batch` (Batch API, 50% off) for the full 50-lead run; .parse isn't
    available in batches, so requests carry a raw output_config.format schema and
    are validated client-side with model_validate_json.
"""

from __future__ import annotations

import logging
from typing import Any

from pipeline import llm
from pipeline.budget import BudgetGuard
from pipeline.config import settings
from pipeline.models import JudgeScore, Usage
from pipeline.prompts import registry

log = logging.getLogger(__name__)


def _user(brief_md: str, job_title: str, subject: str, body: str) -> str:
    # The email is fenced so the judge can't mistake this prompt's own trailing
    # instruction for part of the email it's scoring (observed on the first run:
    # the judge critiqued a "Score it now" CTA that wasn't in the email).
    return (
        f"Hiring signal: {job_title}\n\n"
        f"Research brief:\n{brief_md}\n\n"
        "--- EMAIL UNDER REVIEW (score ONLY the text between the fences) ---\n"
        f"Subject: {subject}\n{body}\n"
        "--- END EMAIL ---\n\n"
        "Return the structured score for the email above."
    )


def judge_one(
    *, brief_md: str, job_title: str, subject: str, body: str,
    version: str = "v1", budget: BudgetGuard | None = None,
) -> tuple[JudgeScore, str]:
    prompt = registry.load("judge_rubric", version)
    score, _ = llm.parse_judge(
        JudgeScore, prompt.text, _user(brief_md, job_title, subject, body),
        max_tokens=800, budget=budget,
    )
    return score, prompt.pv_id


# ── Batch path ───────────────────────────────────────────────────────
def build_batch_request(custom_id: str, *, brief_md: str, job_title: str, subject: str, body: str, version: str = "v1") -> dict[str, Any]:
    """One Batch API request scoring one email touch."""
    prompt = registry.load("judge_rubric", version)
    return {
        "custom_id": custom_id,
        "params": {
            "model": settings.judge_model,
            "max_tokens": 800,
            "system": prompt.text,
            "messages": [{"role": "user", "content": _user(brief_md, job_title, subject, body)}],
            "output_config": {
                "format": {"type": "json_schema", "schema": llm.strict_schema(JudgeScore)}
            },
        },
    }


def parse_batch_result(result: Any) -> JudgeScore | None:
    """Validate one batch result into a JudgeScore (None on error/refusal)."""
    if result.result.type != "succeeded":
        log.warning("batch result %s not succeeded: %s", result.custom_id, result.result.type)
        return None
    for block in result.result.message.content:
        if block.type == "text":
            try:
                return JudgeScore.model_validate_json(block.text)
            except Exception as e:  # noqa: BLE001 — recorded as a failed eval upstream
                log.warning("batch result %s failed JudgeScore validation: %s", result.custom_id, e)
                return None
    return None


def result_usage(result: Any) -> Usage | None:
    """Token usage for one batch result, so the batch judge cost is counted in
    the BudgetGuard (batched=True applies the 50% Batch-API discount)."""
    if result.result.type != "succeeded":
        return None
    u = result.result.message.usage
    return Usage(model=settings.judge_model, input_tokens=u.input_tokens,
                 output_tokens=u.output_tokens, batched=True)
