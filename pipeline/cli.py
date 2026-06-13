"""gtmer CLI — Typer. The orchestrator and the verification surface for each slice.

  gtmer doctor                      # all four integrations green
  gtmer prospect --limit 100        # universe → ATS → qualify → sourced leads
  gtmer run --limit 50              # drive the graph to 'scored'
  gtmer run-one x.com "X"           # positional: DOMAIN COMPANY
  gtmer eval golden                 # judge–human agreement / kappa
  gtmer eval pairwise --a v1 --b v2
  gtmer enrich-top10                # Hunter emails for the top 10 (last mile)
  gtmer report                      # run + stage + cost summary
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, help="PipelineAgent — AI-SDR pipeline for GTMer.")
eval_app = typer.Typer(help="Eval-harness commands.")
app.add_typer(eval_app, name="eval")
console = Console()


def _print(obj) -> None:
    console.print_json(json.dumps(obj, default=str))


@app.command()
def doctor() -> None:
    """Verify Anthropic, Voyage (dim assert), Supabase, and Langfuse."""
    from pipeline.config import settings

    rows: list[tuple[str, str, str]] = []

    # Anthropic
    try:
        from pipeline import llm

        r = llm.client().messages.create(
            model=settings.writer_model, max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        rows.append(("anthropic", "ok", f"{settings.writer_model} → {r.stop_reason}"))
    except Exception as e:  # noqa: BLE001
        rows.append(("anthropic", "FAIL", str(e)))

    # Voyage — assert embedding dim matches the vector(1024) column
    try:
        from pipeline.researcher import embeddings

        dim = embeddings.probe_dim()
        ok = dim == settings.embed_dim
        rows.append(("voyage", "ok" if ok else "FAIL", f"dim={dim} (want {settings.embed_dim})"))
    except Exception as e:  # noqa: BLE001
        rows.append(("voyage", "FAIL", str(e)))

    # Supabase
    try:
        from pipeline import db

        db.client().table("runs").select("id").limit(1).execute()
        rows.append(("supabase", "ok", "runs table reachable"))
    except Exception as e:  # noqa: BLE001
        rows.append(("supabase", "FAIL", str(e)))

    # Langfuse
    try:
        from pipeline import trace

        h = trace.handler()
        trace.flush()
        rows.append(("langfuse", "ok" if h else "skip", "configured" if h else "no keys (optional)"))
    except Exception as e:  # noqa: BLE001
        rows.append(("langfuse", "FAIL", str(e)))

    table = Table("integration", "status", "detail")
    for name, status, detail in rows:
        table.add_row(name, status, detail)
    console.print(table)
    if any(s == "FAIL" for _, s, _ in rows):
        raise typer.Exit(1)


@app.command()
def prospect(limit: int = 100, include_yc: bool = True) -> None:
    """Build the universe, probe ATS boards, qualify, and store sourced leads."""
    from pipeline import runner

    _print(runner.prospect(limit=limit, include_yc=include_yc))


@app.command()
def run(limit: int = typer.Option(None), version: str = "v1", target: str = "scored") -> None:
    """Drive the per-lead graph over sourced leads up to `target`."""
    from pipeline import runner

    _print(runner.run_pipeline(limit=limit, version=version, target=target))


@app.command("run-one")
def run_one(domain: str, company: str, job_title: str = "", job_url: str = typer.Option(None), version: str = "v1") -> None:
    """Walking-skeleton: take one hand-picked lead end-to-end."""
    from pipeline import runner

    _print(runner.run_one(domain=domain, company=company, job_title=job_title, job_url=job_url, version=version))


@eval_app.command("golden")
def eval_golden(version: str = "v1") -> None:
    """Judge–human agreement, Cohen's kappa, per-dim MAE on the golden set."""
    from pipeline.evals import golden

    _print(golden.run(version=version))


@eval_app.command("pairwise")
def eval_pairwise(a: str = "v1", b: str = "v2", n: int = 20) -> None:
    """Randomized pairwise comparison of two writer prompt versions."""
    from pipeline.evals import pairwise

    _print(pairwise.run(a_version=a, b_version=b, n=n))


@app.command("enrich-top10")
def enrich_top10() -> None:
    """Hunter.io email find for the top-10 approved leads (last-mile, ≤15 credits)."""
    from pipeline import enrich

    _print(enrich.enrich_top10())


@app.command("judge-batch")
def judge_batch(version: str = "v1") -> None:
    """Score all drafted leads via the Batch API (50% off) — the 50-lead-run path."""
    from pipeline.evals import batch_runner

    _print(batch_runner.run(version=version))


@app.command()
def report() -> None:
    """Run + stage + cost summary."""
    from pipeline import db

    stages = ["sourced", "researched", "drafted", "scored", "approved", "dead"]
    table = Table("stage", "count")
    for s in stages:
        table.add_row(s, str(len(db.leads_by_stage(s))))
    console.print(table)
    console.print(f"[bold]lifetime LLM spend:[/] ${db.lifetime_spend():.4f}")


if __name__ == "__main__":
    app()
