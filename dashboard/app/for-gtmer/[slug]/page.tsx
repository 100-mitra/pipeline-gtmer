"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { LeadDetail } from "@/lib/types";
import { WarmingBanner } from "@/components/WarmingBanner";
import { LeadDetailView } from "@/components/LeadDetailView";

// The private pitch artifact: top-10 approved leads + drafts + scorecards. The
// unguessable slug (server-validated) is the only privacy mechanism — no auth by
// design. Reads only from Supabase; never invokes the pipeline live.
export default function ForGtmerPage() {
  const params = useParams<{ slug: string }>();
  const [data, setData] = useState<{ count: number; leads: LeadDetail[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.forGtmer(params.slug).then(setData).catch((e) => setErr(e?.message ?? "not found"));
  }, [params.slug]);

  if (err) return <p style={{ color: "var(--bad)" }}>Not found.</p>;
  if (!data) return <WarmingBanner />;

  return (
    <>
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>{data.count} qualified leads for GTMer</h2>
        <p className="muted" style={{ marginBottom: 0 }}>
          Sourced from companies currently hiring SDR/BDR roles (a buying signal for an AI-SDR tool), researched with
          retrieval-grounded briefs, drafted as 3-touch sequences, and eval-scored. <b>Nothing was sent</b> — the
          pipeline stops at &ldquo;approved&rdquo; by design. {data.count} approved.
        </p>
      </div>
      {data.leads.map((d) => (
        <LeadDetailView key={d.lead.id} data={d} />
      ))}
    </>
  );
}
