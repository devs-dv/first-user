// Shapes of a product brief (worker/understand.py writes it; /api/briefs/[id] returns it).

export type ClaimStatus = "confirmed" | "inferred" | "unknown";
export type PricingStatus = "published" | "not_published" | "unclear";

export type BriefClaim = {
  claim: string;
  source_url: string;
  status: ClaimStatus;
  // A short exact quote from the source page; empty unless the claim is confirmed.
  quote: string;
};

export type PricingTier = { name: string; price: string; what_you_get: string; source_url: string };

export type SuggestedJourney = {
  goal: string;
  // How we would know it worked.
  success: string;
  source_url: string;
  basis: "call_to_action" | "claim";
  basis_text: string;
  // A site's claim is a goal to test, never proof that it works.
  claim_to_test: boolean;
};

// Written by the worker's code, not by a model: shown when a page held text hidden from people and addressed to
// automated agents. The brief records where it was found, never the text.
export const HIDDEN_TEXT_NOTICE =
  "This page contains hidden text addressed to automated agents. It is not visible to people and was ignored.";

export type HiddenTextNote = {
  notice: string;
  found: { url: string; where: string; method: string; blocks: number }[];
};

export type Brief = {
  version: number;
  url: string;
  one_liner: string;
  what_it_does: string;
  who_its_for: string;
  how_it_works: string;
  primary_value: string;
  pricing: { status: PricingStatus; tiers: PricingTier[]; note: string; source_urls: string[] };
  business_model: { label: "inferred"; model: string; evidence: { quote: string; source_url: string }[] };
  claims: BriefClaim[];
  unknowns: string[];
  suggested_journeys: SuggestedJourney[];
  pages: { url: string; kind: string; title: string; method: "http" | "browser"; status: number; bytes: number }[];
  skipped: { url: string; kind: string; reason: string }[];
  limits: { seconds: number; browser_reads: number; stopped: string | null };
  hidden_text?: HiddenTextNote | null;
};

// A site that could not be read: the run is "failed" and the brief says why, in words for the visitor.
export type BriefFailure = { status: "could_not_read"; message: string };

export type BriefRun = {
  id: string;
  url: string;
  status: "queued" | "running" | "done" | "failed";
  brief: Brief | BriefFailure | null;
  cost_usd: number | string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

// One string literal, so supabase-js can infer the row type from it.
export const BRIEF_COLUMNS = "id, url, status, brief, cost_usd, created_at, started_at, finished_at";
