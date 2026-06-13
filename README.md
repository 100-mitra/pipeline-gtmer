# PipelineAgent — 10 Meetings for GTMer

An autonomous **AI-SDR pipeline** — prospect → research (RAG) → personalized 3-touch
outreach → **LLM-as-judge evals** → kanban — run on **GTMer's own ICP**. It's a
working miniature of GTMer's product, built so the cold email to the founder doubles
as the deliverable: a list of qualified leads for GTMer's business, each with
eval-scored drafts.

> **Hard rule: nothing is ever sent.** The pipeline stops at `approved`. Deliverability
> is the one way to embarrass yourself cold-emailing a founder who does this for a
> living, so the design makes sending impossible — a human clicks the final approve.

## Why this shape — the anti-11x thesis

The AI-SDR category's cautionary tale is **11x.ai**: a 2025 investigation surfaced
non-customer logos, ARR counted on contracts customers were opting out of, and
70–80% churn; the CEO stepped down. The lesson the whole category absorbed:
**unmeasured output quality is the failure mode.** Meanwhile the capital went to the
human-in-the-loop "GTM engineering" players — Clay (~$3.1B) and Unify ($40M Series B)
— whose workflow shape is exactly *prospect → research → draft → human review*.

So the centerpiece here isn't the agents — it's the **eval harness**. Every draft is
gated by deterministic heuristics, a hallucination/grounding check against retrieved
evidence, and an LLM-as-judge that is itself **validated against a hand-labeled golden
set** (judge–human agreement / Cohen's κ). That's the credibility layer 11x didn't have.

## Architecture

```
              ┌──────────────────────────────────────────────┐
              │  Next.js dashboard (Vercel)                  │
              │  Sourced → Researched → Drafted → Scored →    │
              │  Approved   (+ /for-gtmer pitch page)         │
              └───────────────┬──────────────────────────────┘
                              │ REST (read) + advance (1 mutation)
              ┌───────────────┴──────────────────────────────┐
              │  FastAPI (Render free)  — reads Supabase only │
              └───────────────┬──────────────────────────────┘
                              │
   gtmer CLI ───────►  LangGraph per-lead StateGraph (Python)
                              │
   scrape → embed → research_brief → write_sequence → run_evals → END
       │        │         │ (RAG)        │ (3×2)        │ (cascade)
    httpx/    Voyage   match_chunks    Haiku writer   heuristics→grounding→Sonnet judge
   Firecrawl  voyage-4  RPC (pgvector)                          │
       └── cache ──┘                                      golden-set κ gate
                              │
                   Supabase (Postgres + pgvector)  ·  Langfuse traces/cost
```

- **Writer ≠ Judge** (anti self-preference bias): writer = `claude-haiku-4-5` ($1/$5),
  judge = `claude-sonnet-4-6` ($3/$15) — a stronger, different-tier model judges the cheaper writer.
- **Structured outputs everywhere** via native `client.messages.parse(output_format=…)`
  + Pydantic; malformed output surfaces, never silently passes.
- **Idempotent + resumable:** scraped pages cached by URL hash; brief/email/eval rows
  keyed by `(lead, prompt_version)`; re-running a finished run is a no-op.
- **Budget guard** checks spend *before* every LLM call — a per-run cap and a lifetime
  `$20` hard cap, so a retry storm can't overrun.
- **Dead-letter, never crash the batch:** any node error routes the lead to a terminal
  `dead` stage with a reason; the orchestrator moves to the next lead.

## Lead sourcing — what's ToS-safe, and what isn't

Companies **hiring SDR/BDR reps are investing in outbound** — the exact buying signal
for an AI-SDR tool, and job postings are public data. Sourcing uses **public ATS JSON
APIs** (no auth, vendor-sanctioned):

| Source | Endpoint | Status |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | ✅ public, no auth |
| Lever | `api.lever.co/v0/postings/{token}?mode=json` | ✅ public, no auth |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{token}` | ✅ public, no auth |

Company universe = a hand-curated CSV of Indian B2B SaaS (`data/companies_in.csv`,
the primary seed) + the `yc-oss` static YC dataset (filtered to India client-side).

**Deliberately excluded** (documented because *judgment* is the point):
Wellfound (DataDome — 403s all automated access), Naukri (edge-blocks non-browser
traffic), Cutshort (ToS bans automated collection), Google SERP scraping (ToS), and
the Google Custom Search JSON API (closed to new customers, discontinued Jan 2027).
LinkedIn URLs are added **manually** for the final top-10 only.

## Eval methodology (the part most candidates skip)

1. **Heuristics** (free, deterministic, run first) — word-count bounds, spam-word and
   banned-phrase blocklists, placeholder-leak regex, must-reference-the-hiring-signal,
   single-CTA. A failure **skips the paid stages**.
2. **Grounding** — Haiku extracts the email's factual claims about the prospect; each is
   matched against retrieved chunks (`match_chunks` RPC) and entailment-checked. **Any**
   unsupported claim fails the email (zero-hallucination policy).
3. **LLM-as-judge** — Sonnet scores 5 dimensions (personalization, relevance-to-signal,
   clarity, CTA, spam-risk) + a verdict. Batched through the Anthropic **Batch API
   (50% off)** for the full run.
4. **Judge validation** — `gtmer eval golden` runs the judge over ~20 hand-labeled emails
   and reports verdict agreement, **Cohen's κ**, and per-dimension MAE. **Gate: κ ≥ 0.6**
   before batch scores are trusted. Prompt-version decisions use **randomized pairwise
   comparison** (`gtmer eval pairwise`, A/B order shuffled to kill position bias), not
   absolute scores — see `prompts/v1` vs `prompts/v2`.

## Cost

~$3.40–4.70 per full 50-lead run (briefs ~$0.70, drafts ~$0.60, batched judge ~$1.80,
grounding ~$0.30; Voyage embeddings $0 on the 200M-token free tier). ~5 full runs fit
under the `$20` hard cap. Tracked live in Langfuse + the local budget meter.

## Stack & cost (all free-tier)

| Piece | Choice |
|---|---|
| Agents | Python 3.11+, LangGraph 1.2 (Graph API), Pydantic v2 |
| LLM | Haiku 4.5 (writer) · Sonnet 4.6 (judge) — Anthropic |
| Embeddings | Voyage `voyage-4-lite` (200M free tokens) |
| RAG / DB / auth | Supabase (Postgres + pgvector), HTTPS RPC |
| Observability | Langfuse Cloud (Hobby) |
| Backend | FastAPI on Render (free) |
| Frontend | Next.js on Vercel (Hobby) |
| Scraping | httpx + BeautifulSoup; Firecrawl fallback |
| Email find | Hunter.io free (top-10 last mile only) |

## Run it

Prereqs: Python 3.12, Node.js 18+ (dashboard), a Supabase project, Anthropic + Voyage keys.

```powershell
# 1. backend
cd C:\dev\gtmer-pipeline
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env            # fill in keys; generate FOR_GTMER_SLUG
$env:PYTHONUTF8 = "1"
# apply supabase/migrations/0001_init.sql in the Supabase SQL editor

python -m pipeline.cli doctor                       # all integrations green (asserts embed dim == 1024)
python -m pipeline.cli prospect --limit 100         # universe → ATS → qualify → sourced leads
python -m pipeline.cli run --limit 50               # graph to 'scored' (sync judge)
python -m pipeline.cli judge-batch                  # OR the 50%-off Batch API judge path
python -m pipeline.cli eval golden                  # judge–human κ (gate ≥ 0.6)
python -m pipeline.cli eval pairwise --a v1 --b v2  # promote a writer prompt on evidence
python -m pipeline.cli report                       # funnel + lifetime spend

uvicorn pipeline.api.main:app --port 8000           # read API

# 2. dashboard
cd dashboard ; npm install ; copy .env.local.example .env.local ; npm run dev
```

Tests (no keys needed): `pytest -q` → 17 passing (ATS parsers, qualify regex, heuristics).

## What I'd build next at GTMer

- **Voice qualification** (Vapi): a stretch agent that calls a prospect, asks 3
  qualification questions, returns a structured lead score — closing the email/LinkedIn/call triad.
- **Send-layer integration** (Smartlead/Instantly) behind the approve gate, with warmup
  + deliverability handled, so `approved` → actually-sent stays a one-line swap with guardrails.
- **Reply-driven learning loop:** feed reply/positive-reply outcomes back as labels and
  let pairwise drive automatic prompt promotion — evals become a flywheel, not a snapshot.
- **Intent enrichment:** funding/job-change/tech-stack triggers to tier the signal, mirroring Unify's funded architecture.

## Risks & honest limitations

| Risk | Mitigation |
|---|---|
| < 10 strong leads (sparse live SDR postings) | curated CSV is primary; widen title regex; tier signals; probe 100+ |
| Judge unreliable (κ < 0.6) | golden-set gate before trusting scores; pairwise for decisions; human approve-stage |
| Lead data stale / wrong contact | score evidence; Hunter marks verified vs guessed; emails manual on top-10 only |
| Scraping blocked / JS-heavy | Firecrawl fallback; cache; skip-and-flag, never block the batch |
| Budget overrun | check before every call; truncate page text; cap retries; batched judge; $20 hard cap |
| Demo-day infra flakiness | keep-alive crons (Supabase pause, Render spin-down); /for-gtmer reads only from Supabase |

## Privacy

Contact emails are redacted in any public demo/repo; full contact data lives only in the
private `/for-gtmer/<slug>` deliverable. Scraping respects robots.txt and uses public,
vendor-sanctioned endpoints only.
