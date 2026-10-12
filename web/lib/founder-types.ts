// Shapes of a founder brief (worker/founder_brief.py writes it; /api/briefs/[id]/founder returns it).

import type { HiddenTextNote } from "./brief-types.ts";

// Fixed: the worker writes the same text, and the page shows this one whatever the data says.
export const FOUNDER_NOTE =
  "Built only from the public website. It cannot judge the team, real demand, revenue or retention.";
export const TRACTION_LABEL = "Stated by the company, not verified";
export const ASSESSMENT_LABEL = "Our assessment";

export type FounderSource = { url: string; quote: string };

// A sentence with the pages it rests on. "unknown" has no sources.
export type FounderStatement = {
  text: string;
  sources: FounderSource[];
  status: "stated" | "assessment" | "unknown";
  label?: string;
};

export type ReadinessDimension = {
  dimension: string;
  label: string;
  shows: FounderStatement[];
  unknown: string[];
  question: string;
};

export type FounderBrief = {
  version: number;
  kind: "founder_brief";
  note: string;
  url: string;
  source_brief_id: string | null;
  hidden_text?: HiddenTextNote | null;
  executive_summary: Record<"building" | "for_whom" | "problem" | "solution" | "business_model", FounderStatement>;
  opportunity: {
    problem: FounderStatement;
    alternatives: { name: string; sources: FounderSource[] }[];
    target_users: FounderStatement;
    why_different: FounderStatement;
  };
  product_and_business_model: {
    core_features: FounderStatement[];
    maturity_signals: FounderStatement[];
    pricing: {
      status: "published" | "not_published" | "unclear";
      tiers: { name: string; price: string; what_you_get: string; source_url: string }[];
      note: string;
    };
    business_model: { label: "inferred"; model: string; evidence: { quote: string; source_url: string }[] };
  };
  evidence_and_risks: {
    traction: { claim: string; quote: string; source_url: string; label: string }[];
    traction_label: string;
    missing_evidence: string[];
    risks: Record<"technical" | "competitive" | "go_to_market", FounderStatement[]>;
    risks_label: string;
  };
  readiness: ReadinessDimension[];
  pages_read: string[];
};

export type FounderFailure = { status: "could_not_write"; message: string };

export type FounderRun = {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  brief: FounderBrief | FounderFailure | null;
  created_at: string;
  finished_at: string | null;
};

export function isFounderBrief(value: unknown): value is FounderBrief {
  const brief = value as FounderBrief | null;
  return !!brief && typeof brief === "object" && brief.kind === "founder_brief" && Array.isArray(brief.readiness);
}

export function isFounderFailure(value: unknown): value is FounderFailure {
  const failure = value as FounderFailure | null;
  return !!failure && typeof failure === "object" && failure.status === "could_not_write";
}

export const FOUNDER_COLUMNS = "id, status, brief, created_at, finished_at";
