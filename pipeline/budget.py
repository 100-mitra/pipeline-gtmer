"""Budget guard — the authoritative spend gate.

Langfuse tracks cost for observability, but its async ingest + 30-day retention
make it unfit as an enforcement gate. This local counter is the source of truth:
`check()` runs BEFORE every LLM call and raises `BudgetExceeded` once the run
(or lifetime) cap is hit, so a retry storm or a scrape-heavy lead can't blow the
$20 ceiling.
"""

from __future__ import annotations

from pipeline.config import BATCH_DISCOUNT, MODEL_PRICES, settings
from pipeline.models import Usage


class BudgetExceeded(Exception):
    """Raised before a call that would push spend past a configured cap."""


def usage_cost(usage: Usage) -> float:
    """USD cost of one Usage record."""
    in_price, out_price = MODEL_PRICES.get(usage.model, (0.0, 0.0))
    cost = (usage.input_tokens / 1_000_000) * in_price + (
        usage.output_tokens / 1_000_000
    ) * out_price
    return cost * BATCH_DISCOUNT if usage.batched else cost


class BudgetGuard:
    """Per-run cost meter. `lifetime_spent` lets a second cap span all runs."""

    def __init__(
        self,
        run_cap_usd: float | None = None,
        hard_cap_usd: float | None = None,
        lifetime_spent: float = 0.0,
    ) -> None:
        self.run_cap = run_cap_usd if run_cap_usd is not None else settings.budget_run_usd
        self.hard_cap = (
            hard_cap_usd if hard_cap_usd is not None else settings.budget_hard_cap_usd
        )
        self.lifetime_spent = lifetime_spent
        self.run_spent = 0.0
        self.input_tokens = 0
        self.output_tokens = 0

    def check(self, estimated: float = 0.0) -> None:
        """Call BEFORE an LLM request. `estimated` is an optional headroom guess."""
        if self.run_spent + estimated > self.run_cap:
            raise BudgetExceeded(
                f"run cap ${self.run_cap:.2f} reached (spent ${self.run_spent:.4f})"
            )
        if self.lifetime_spent + self.run_spent + estimated > self.hard_cap:
            raise BudgetExceeded(
                f"hard cap ${self.hard_cap:.2f} reached "
                f"(lifetime ${self.lifetime_spent + self.run_spent:.4f})"
            )

    def record(self, usage: Usage) -> float:
        """Call AFTER each response. Returns the marginal cost."""
        cost = usage_cost(usage)
        self.run_spent += cost
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        return cost
