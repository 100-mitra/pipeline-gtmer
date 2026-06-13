"""Voyage AI embeddings (voyage-4-lite — 200M free tokens ≈ $0 for this project).

`doctor()` calls `embed_query` with a probe string and asserts the returned
dimension matches `settings.embed_dim` / the `vector(1024)` column, so a model
swap is caught before any data is written.
"""

from __future__ import annotations

import functools

import voyageai
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pipeline.config import settings


@functools.lru_cache(maxsize=1)
def _client() -> voyageai.Client:
    if not settings.voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    return voyageai.Client(api_key=settings.voyage_api_key)


def _is_rate_limit(e: BaseException) -> bool:
    return getattr(e, "http_status", None) == 429 or "ratelimit" in type(e).__name__.lower()


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, max=30),
    retry=retry_if_exception(_is_rate_limit),
    reraise=True,
)
def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    """Voyage embed with backoff on 429s (the free tier without a card is capped
    at 3 RPM / 10K TPM; backoff rides out a transient throttle window)."""
    result = _client().embed(texts, model=settings.embed_model, input_type=input_type)
    vecs = result.embeddings
    if len(vecs) != len(texts):  # contract guard — never silently lose a chunk
        raise RuntimeError(f"Voyage returned {len(vecs)} vectors for {len(texts)} texts")
    return vecs


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _embed(texts, "document")


def embed_query(text: str) -> list[float]:
    return _embed([text], "query")[0]


def probe_dim() -> int:
    """Return the live embedding dimension (used by `gtmer doctor`)."""
    return len(embed_query("dimension probe"))
