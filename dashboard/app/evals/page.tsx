"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { EvalsSummary } from "@/lib/types";
import { WarmingBanner } from "@/components/WarmingBanner";

function pct(x: number | null) {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

export default function EvalsPage() {
  const [s, setS] = useState<EvalsSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.evalsSummary().then(setS).catch((e) => setErr(e?.message ?? "error"));
  }, []);

  if (err) return <p style={{ color: "var(--bad)" }}>Error: {err}</p>;
  if (!s) return <WarmingBanner />;

  return (
    <>
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Eval summary</h2>
        <div>
          <span className="stat"><div className="n" style={{ color: "var(--good)" }}>{s.judge_kappa ?? "—"}</div><div className="l">judge κ vs human</div></span>
          <span className="stat"><div className="n">{pct(s.heuristic_pass_rate)}</div><div className="l">heuristic pass</div></span>
          <span className="stat"><div className="n">{pct(s.grounding_pass_rate)}</div><div className="l">grounding pass</div></span>
          <span className="stat"><div className="n">{s.avg_judge_overall ?? "—"}</div><div className="l">avg judge / 5</div></span>
          <span className="stat"><div className="n">${s.total_cost_usd.toFixed(2)}</div><div className="l">total LLM spend</div></span>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Judge–human agreement (Cohen&apos;s κ) is computed by <code>gtmer eval golden</code> against the hand-labeled
          golden set; the gate is κ ≥ 0.6 before batch judge scores are trusted. Prompt-version decisions use randomized
          pairwise comparison (<code>gtmer eval pairwise</code>), not absolute scores.
        </p>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>Pipeline funnel</h3>
        <table>
          <tbody>
            {Object.entries(s.leads_by_stage).map(([stage, n]) => (
              <tr key={stage}>
                <td>{stage}</td>
                <td>{n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
