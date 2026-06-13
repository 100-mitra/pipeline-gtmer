export type Stage = "sourced" | "researched" | "drafted" | "scored" | "approved" | "dead";

export interface LeadCard {
  id: string;
  company_name: string;
  domain: string;
  stage: Stage;
  job_title?: string | null;
  signal_score?: number | null;
  signal_tier?: string | null;
}

export interface KanbanColumn {
  stage: Stage;
  leads: LeadCard[];
}

export interface Citation {
  n: number;
  url: string;
  quote?: string;
}

export interface Brief {
  content_md: string;
  citations: Citation[];
}

export interface Email {
  id: string;
  variant: "A" | "B";
  touch: number;
  subject: string;
  body: string;
}

export interface EvalRow {
  id: string;
  email_id: string | null;
  kind: "heuristic" | "grounding" | "judge" | "human" | "pairwise";
  passed: boolean | null;
  scores: any;
  overall: number | null;
  feedback: string | null;
}

export interface LeadDetail {
  lead: any;
  brief: Brief | null;
  emails: Email[];
  evals: EvalRow[];
}

export interface EvalsSummary {
  leads_by_stage: Record<string, number>;
  heuristic_pass_rate: number | null;
  grounding_pass_rate: number | null;
  avg_judge_overall: number | null;
  judge_kappa: number | null;
  total_cost_usd: number;
}
