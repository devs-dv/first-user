// Shapes returned by GET /api/runs/[id]. Shared by the API route and the run page.

export type RunStatus = "queued" | "running" | "done" | "failed";
export type Outcome =
  | "achieved"
  | "achieved_unconfirmed"
  | "not_achieved"
  | "unverified"
  | "gave_up"
  | "blocked"
  | "max_steps"
  | "error";

export type Clarity = "yes" | "partly" | "no";

// What a newcomer sees on the landing page without logging in (written by the worker).
export type FirstImpression = {
  what_it_does: { clear: Clarity; summary: string };
  who_its_for: { clear: Clarity; summary: string };
  main_action: { obvious: Clarity; summary: string };
  hesitations: string[];
  suggestions: string[];
};

// Which way in the visit used. Never holds a credential: the test login's values are not stored here.
export type Entry = {
  start_link: string | null;
  test_login: "not_provided" | "provided_not_used" | "used" | "failed";
  self_signup: "not_used" | "used" | "blocked_verification" | "blocked_third_party" | "failed";
  third_party_options: string[];
  created_account_email: string | null;
  blocked_at_login: boolean;
};

export type Run = {
  id: string;
  url: string;
  start_url: string | null;
  has_test_login: boolean;
  first_impression: FirstImpression | null;
  entry: Entry | null;
  goal: string;
  status: RunStatus;
  outcome: Outcome | null;
  reason: string | null;
  cost_usd: number | string | null;
  brain_model: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Step = {
  idx: number;
  tool: string;
  thought: string | null;
  input: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  url: string | null;
  screenshot_path: string | null;
  created_at: string;
};

export type Friction = {
  id: number;
  step_idx: number | null;
  kind: "site" | "agent_issue";
  severity: "low" | "medium" | "high" | null;
  expected: string | null;
  happened: string | null;
};

export type RunDetails = { run: Run; steps: Step[]; frictions: Friction[] };

export type ApiError = { error: string; message: string };

// Never includes the test login: it lives in run_secrets, which the web app never reads.
// One string literal, so supabase-js can infer the row type from it.
export const RUN_COLUMNS =
  "id, url, start_url, has_test_login, first_impression, entry, goal, status, outcome, reason, cost_usd, brain_model, created_at, started_at, finished_at";
export const STEP_COLUMNS = "idx, tool, thought, input, result, url, screenshot_path, created_at";
export const FRICTION_COLUMNS = "id, step_idx, kind, severity, expected, happened";
