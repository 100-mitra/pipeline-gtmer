"use client";

import type { Email, EvalRow, LeadDetail } from "@/lib/types";

const DIMS = ["personalization", "relevance_to_signal", "clarity", "cta_quality", "spam_risk"];

function Scorecard({ evals }: { evals: EvalRow[] }) {
  const h = evals.find((e) => e.kind === "heuristic");
  const g = evals.find((e) => e.kind === "grounding");
  const j = evals.find((e) => e.kind === "judge");
  return (
    <div className="score">
      <span className={`badge ${h?.passed ? "pass" : "fail"}`}>heuristics {h?.passed ? "pass" : "fail"}</span>
      <span className={`badge ${g?.passed ? "pass" : "fail"}`}>grounding {g?.passed ? "pass" : "fail"}</span>
      {j?.scores &&
        DIMS.map((d) => (
          <span className="dim" key={d}>
            {d.replace(/_/g, " ")}: <b>{j.scores[d]}</b>
          </span>
        ))}
      {j?.scores?.verdict && <span className="dim">verdict: <b>{j.scores.verdict}</b></span>}
      {j?.overall != null && <span className="dim">overall: <b>{j.overall}</b>/5</span>}
    </div>
  );
}

export function LeadDetailView({ data }: { data: LeadDetail }) {
  const { lead, brief, emails, evals } = data;
  const evalsByEmail = (id: string) => evals.filter((e) => e.email_id === id);
  const variants = ["A", "B"] as const;

  return (
    <>
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>
          {lead.company_name} <span className="muted">· {lead.domain}</span>
        </h2>
        <div className="meta">
          stage <b>{lead.stage}</b> · signal {lead.signal_tier ?? "—"} ({lead.signal_score ?? "—"})
          {lead.job_title && <> · hiring: {lead.job_title}</>}
        </div>
      </div>

      {brief && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Research brief (RAG, cited)</h3>
          <div className="body" style={{ whiteSpace: "pre-wrap" }}>{brief.content_md}</div>
          <ol className="meta" style={{ marginTop: 10 }}>
            {brief.citations.map((c) => (
              <li key={c.n}>
                <a href={c.url} target="_blank" rel="noreferrer">{c.url}</a>
                {c.quote ? ` — "${c.quote}"` : ""}
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="grid2">
        {variants.map((v) => (
          <div className="panel" key={v}>
            <h3 style={{ marginTop: 0 }}>Variant {v}</h3>
            {emails
              .filter((e: Email) => e.variant === v)
              .sort((a, b) => a.touch - b.touch)
              .map((e) => (
                <div className="email" key={e.id}>
                  <div className="touchlabel">Touch {e.touch}</div>
                  <div className="subj">{e.subject}</div>
                  <div className="body">{e.body}</div>
                  <Scorecard evals={evalsByEmail(e.id)} />
                </div>
              ))}
          </div>
        ))}
      </div>
    </>
  );
}
