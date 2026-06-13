"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { KanbanColumn, LeadCard, Stage } from "@/lib/types";
import { WarmingBanner } from "@/components/WarmingBanner";

const NEXT: Record<Stage, Stage | null> = {
  sourced: "researched",
  researched: "drafted",
  drafted: "scored",
  scored: "approved",
  approved: null,
  dead: null,
};

export default function KanbanPage() {
  const [cols, setCols] = useState<KanbanColumn[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      setCols(await api.leads());
    } catch (e: any) {
      setErr(e?.message ?? "failed to load");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function advance(lead: LeadCard) {
    const to = NEXT[lead.stage];
    if (!to) return;
    try {
      await api.advance(lead.id, to);
      await load();
    } catch (e: any) {
      alert(`Can't advance: ${e?.message ?? "error"}`);
    }
  }

  if (err) return <p style={{ color: "var(--bad)" }}>Error: {err}</p>;
  if (!cols) return <WarmingBanner />;

  return (
    <div className="board">
      {cols.map((col) => (
        <div className="col" key={col.stage}>
          <h3>
            {col.stage} · {col.leads.length}
          </h3>
          {col.leads.map((lead) => (
            <div className="card" key={lead.id}>
              <Link href={`/leads/${lead.id}`} className="co">
                {lead.company_name}
              </Link>
              <div className="meta">
                {lead.job_title ?? "—"}
                {lead.signal_tier && <> · <span className={`tier ${lead.signal_tier}`}>{lead.signal_tier}</span></>}
              </div>
              {NEXT[lead.stage] && (
                <button className="adv" onClick={() => advance(lead)}>
                  → {NEXT[lead.stage]}
                </button>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
