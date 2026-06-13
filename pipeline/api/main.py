"""FastAPI app — read-only API for the dashboard + the slug-gated pitch page.

No auth (single hardcoded workspace by design). CORS allows the Vercel dashboard
and localhost. The API only reads Supabase; the pipeline runs locally.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pipeline.api.routes import router

app = FastAPI(title="PipelineAgent API", version="0.1.0")

_origins = ["http://localhost:3000"]
if (vercel := os.environ.get("DASHBOARD_ORIGIN")):
    _origins.append(vercel)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
