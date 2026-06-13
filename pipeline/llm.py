"""Anthropic wrappers — structured outputs via native `messages.parse`.

Every LLM call flows through `parse()`, which:
  1. checks the BudgetGuard BEFORE the request (so a cap is never breached),
  2. retries transient errors (tenacity) but never retries a 400,
  3. records token usage into the guard AFTER the response.

Batch helpers (`batch_*`) drive the 50%-off Batch API for the bulk judge pass.
`.parse()` is unavailable inside batches, so batch requests carry a raw
`output_config.format` json_schema and are validated client-side.
"""

from __future__ import annotations

from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pipeline.budget import BudgetGuard
from pipeline.config import settings
from pipeline.models import Usage

T = TypeVar("T", bound=BaseModel)

_RETRYABLE = (anthropic.APIConnectionError, anthropic.InternalServerError, anthropic.RateLimitError)


def client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _usage(model: str, resp: Any) -> Usage:
    u = resp.usage
    return Usage(model=model, input_tokens=u.input_tokens, output_tokens=u.output_tokens)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def parse(
    *,
    model: str,
    output_format: type[T],
    system: str,
    user: str,
    max_tokens: int = 1500,
    budget: BudgetGuard | None = None,
) -> tuple[T, Usage]:
    """Structured call → validated Pydantic instance + Usage. Budget-gated."""
    if budget is not None:
        budget.check()
    resp = client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=output_format,
    )
    usage = _usage(model, resp)
    if budget is not None:
        budget.record(usage)
    parsed = resp.parsed_output
    if parsed is None:  # refusal or schema miss — surface, don't pretend success
        raise RuntimeError(f"{model} returned no parsed output (stop_reason={resp.stop_reason})")
    return parsed, usage


def parse_writer(output_format: type[T], system: str, user: str, **kw: Any) -> tuple[T, Usage]:
    return parse(model=settings.writer_model, output_format=output_format, system=system, user=user, **kw)


def parse_judge(output_format: type[T], system: str, user: str, **kw: Any) -> tuple[T, Usage]:
    return parse(model=settings.judge_model, output_format=output_format, system=system, user=user, **kw)


# ── Batch API (50% off) — bulk judge pass ────────────────────────────
def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic json-schema → Anthropic structured-output shape.

    Anthropic requires `additionalProperties: false` on every object and rejects
    numeric min/max (we avoid those via Literal). Inlines $defs/$ref.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return resolve(defs[name])
            node = {k: resolve(v) for k, v in node.items()}
            if node.get("type") == "object":
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def batch_create(requests: list[dict[str, Any]]) -> str:
    """requests: [{custom_id, params}]; params is a Messages create dict."""
    batch = client().messages.batches.create(requests=requests)  # type: ignore[arg-type]
    return batch.id


def batch_ready(batch_id: str) -> bool:
    return client().messages.batches.retrieve(batch_id).processing_status == "ended"


def batch_results(batch_id: str) -> list[Any]:
    return list(client().messages.batches.results(batch_id))
