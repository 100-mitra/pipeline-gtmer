-- PipelineAgent schema — apply once in the Supabase SQL editor.
-- All Python access goes through supabase-py REST / RPC (no direct Postgres
-- connection), which sidesteps the Windows IPv6-only direct-connect issue.

create extension if not exists vector;

-- ── runs ─────────────────────────────────────────────────────────
create table if not exists runs (
  id               uuid primary key default gen_random_uuid(),
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  status           text not null default 'running',   -- running|completed|aborted_budget|failed
  leads_attempted  int default 0,
  leads_completed  int default 0,
  input_tokens     bigint default 0,
  output_tokens    bigint default 0,
  est_cost_usd     numeric(8,4) default 0,
  notes            text
);

-- ── leads ────────────────────────────────────────────────────────
create table if not exists leads (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid references runs(id),
  company_name  text not null,
  domain        text not null unique,
  ats_source    text,                                  -- greenhouse|lever|ashby|manual
  ats_token     text,
  job_title     text,                                  -- the SDR/BDR posting = buying signal
  job_url       text,
  job_posted_at timestamptz,
  signal_score  int,                                   -- qualification score (prospector)
  signal_tier   text,                                  -- hot|warm|cold
  hq_location   text,
  stage         text not null default 'sourced',       -- sourced|researched|drafted|scored|approved|dead
  dead_reason   text,
  linkedin_url  text,                                  -- manual, top-10 only
  contact_name  text,                                  -- Hunter, top-10 only
  contact_email text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists leads_stage_idx on leads (stage);

-- ── brief_chunks (RAG store) ─────────────────────────────────────
-- embedding dim MUST match EMBED_DIM (voyage-4-lite = 1024). `gtmer doctor`
-- asserts this against a live embed call before any data is written.
create table if not exists brief_chunks (
  id          uuid primary key default gen_random_uuid(),
  lead_id     uuid not null references leads(id) on delete cascade,
  url         text not null,
  chunk_index int not null,
  content     text not null,
  embedding   vector(1024),
  created_at  timestamptz not null default now()
);
create index if not exists brief_chunks_lead_idx on brief_chunks (lead_id);
create index if not exists brief_chunks_embedding_idx
  on brief_chunks using hnsw (embedding vector_cosine_ops);

-- ── briefs ───────────────────────────────────────────────────────
create table if not exists briefs (
  id             uuid primary key default gen_random_uuid(),
  lead_id        uuid not null references leads(id) on delete cascade,
  content_md     text not null,                        -- cited markdown; claims carry [n]
  citations      jsonb not null default '[]',          -- [{"n":1,"url":"...","quote":"..."}]
  prompt_version text not null,
  model          text not null,
  input_tokens   int,
  output_tokens  int,
  created_at     timestamptz not null default now(),
  unique (lead_id, prompt_version)                      -- idempotent regen per prompt version
);

-- ── emails ───────────────────────────────────────────────────────
create table if not exists emails (
  id             uuid primary key default gen_random_uuid(),
  lead_id        uuid not null references leads(id) on delete cascade,
  variant        text not null check (variant in ('A','B')),
  touch          int  not null check (touch between 1 and 3),
  subject        text not null,
  body           text not null,
  prompt_version text not null,
  model          text not null,
  created_at     timestamptz not null default now(),
  unique (lead_id, variant, touch, prompt_version)      -- idempotent re-runs
);

-- ── evals ────────────────────────────────────────────────────────
create table if not exists evals (
  id             uuid primary key default gen_random_uuid(),
  email_id       uuid references emails(id) on delete cascade,
  lead_id        uuid references leads(id) on delete cascade,
  kind           text not null,                         -- heuristic|grounding|judge|human|pairwise
  passed         boolean,
  scores         jsonb,                                 -- judge dims / heuristic detail / pairwise winner
  overall        numeric(4,2),
  feedback       text,
  judge_model    text,
  prompt_version text,                                  -- version of the judged prompt
  created_at     timestamptz not null default now()
);
create index if not exists evals_email_idx on evals (email_id);
create index if not exists evals_lead_idx  on evals (lead_id);

-- ── prompt_versions ──────────────────────────────────────────────
create table if not exists prompt_versions (
  id         text primary key,                          -- 'email_sequence:v1'
  task       text not null,
  version    text not null,
  sha256     text not null,
  active     boolean not null default false,
  notes      text,
  created_at timestamptz not null default now()
);

-- ── match_chunks RPC — vector search over HTTPS (no direct DB conn) ─
create or replace function match_chunks(
  p_lead_id          uuid,
  p_query_embedding  vector(1024),
  p_match_count      int default 6
)
returns table (id uuid, url text, content text, similarity float)
language sql stable
as $$
  select c.id, c.url, c.content,
         1 - (c.embedding <=> p_query_embedding) as similarity
  from brief_chunks c
  where c.lead_id = p_lead_id
  order by c.embedding <=> p_query_embedding
  limit p_match_count;
$$;
