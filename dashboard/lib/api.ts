// Typed fetchers against the FastAPI backend, with cold-start retry/backoff:
// Render free web services spin down after 15 min idle (~1 min cold start), so
// the first request may hang or 502. We retry a few times before surfacing an error.

import type { EvalsSummary, KanbanColumn, LeadDetail } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getJSON<T>(path: string, retries = 4): Promise<T> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
      if (res.ok) return (await res.json()) as T;
      if (res.status < 500) throw new Error(`${res.status} ${res.statusText}`);
      lastErr = new Error(`${res.status}`);
    } catch (e) {
      lastErr = e;
    }
    // backoff: 0.8s, 1.6s, 3.2s, 6.4s — covers a Render cold start
    await new Promise((r) => setTimeout(r, 800 * 2 ** attempt));
  }
  throw lastErr;
}

export const api = {
  base: BASE,
  leads: () => getJSON<KanbanColumn[]>("/api/leads"),
  lead: (id: string) => getJSON<LeadDetail>(`/api/leads/${id}`),
  evalsSummary: () => getJSON<EvalsSummary>("/api/evals/summary"),
  forGtmer: (slug: string) => getJSON<{ count: number; leads: LeadDetail[] }>(`/api/for-gtmer/${slug}`),
  advance: async (id: string, to_stage: string) => {
    const res = await fetch(`${BASE}/api/leads/${id}/advance`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ to_stage }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
    return res.json();
  },
};
