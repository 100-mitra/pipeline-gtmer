"""Central configuration. Loads from environment / .env via pydantic-settings.

Importing this module also forces UTF-8 stdout/stderr on Windows, where the
default cp1252 console raises UnicodeEncodeError when printing LLM output that
contains emoji or smart quotes.
"""

from __future__ import annotations

import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Windows console UTF-8 guard ──────────────────────────────────────
# PYTHONUTF8=1 in .env is the durable fix, but reconfigure here too so a
# forgotten env var doesn't crash a long pipeline run mid-print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


# Per-million-token prices (USD), June 2026. Used by BudgetGuard / cost accounting.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    # model_id: (input_per_mtok, output_per_mtok)
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}
BATCH_DISCOUNT = 0.5  # Anthropic Batch API: 50% off input and output.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM / embeddings
    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    # Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Optional enrichment
    firecrawl_api_key: str = ""
    hunter_api_key: str = ""

    # Models & budget
    writer_model: str = "claude-haiku-4-5"
    judge_model: str = "claude-sonnet-4-6"
    embed_model: str = "voyage-4-lite"
    embed_dim: int = 1024
    budget_run_usd: float = Field(default=5.0)
    budget_hard_cap_usd: float = Field(default=20.0)

    # Pitch page
    for_gtmer_slug: str = ""

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def firecrawl_enabled(self) -> bool:
        return bool(self.firecrawl_api_key)


settings = Settings()


# Langfuse's SDK reads LANGFUSE_* from os.environ directly (its zero-arg
# CallbackHandler / get_client singleton). pydantic-settings loads .env into the
# `settings` object but does NOT populate os.environ, so without this export the
# tracer silently disables itself even when the keys are present in .env.
import os as _os  # noqa: E402

if settings.langfuse_public_key and settings.langfuse_secret_key:
    _os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    _os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    _os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
