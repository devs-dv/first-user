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

// How the founder chose to let the visitor in (the form's "How should the visitor get in?").
export type AccessMode = "public" | "link" | "account" | "signup";

// What a newcomer sees on the landing page without logging in (written by the worker).
export type FirstImpression = {
  what_it_does: { clear: Clarity; summary: string };
  who_its_for: { clear: Clarity; summary: string };
  main_action: { obvious: Clarity; summary: string };
  hesitations: string[];
  suggestions: string[];
};

// What happened after the visitor submitted a login or sign-up form (worker/login_diagnosis.py).
export type LoginDiagnosis = {
  stage: "sign_in" | "sign_up";
  result: "signed_in" | "rejected" | "needs_verification" | "no_effect";
  challenge: "email_verification" | "captcha" | "two_factor" | null;
  page_message: string | null;
  http_statuses: string[];
  step: number | null;
  url: string | null;
  detail?: string;
};

// Which way in the visit used. Never holds a credential: the test login's values are not stored here.
export type Entry = {
  start_link: string | null;
  access_mode?: AccessMode;
  // A login written on the page itself (a demo login for visitors), typed with the page's own values.
  page_login?: "not_used" | "shown_on_page" | "typed";
  // That login was accepted: the password field went away and the visit moved on. Absent on older runs.
  page_login_worked?: boolean;
  diagnosis?: LoginDiagnosis | null;
  // The site showed a bot check ("Verify you are human"); the visit did not try to get past it.
  bot_check?: { phrase: string; url: string; title: string; step: number } | null;
  test_login: "not_provided" | "provided_not_used" | "used" | "failed";
  self_signup: "not_used" | "used" | "blocked_verification" | "blocked_third_party" | "failed";
  third_party_options: string[];
  created_account_email: string | null;
  blocked_at_login: boolean;
};

// One ranked problem from the report writer (worker/report_writer.py). Every one points at a real step.
export type Finding = {
  title: string;
  severity: "high" | "medium" | "low";
  kind: "site_problem" | "unclear_wording" | "hidden_error";
  expected: string;
  happened: string;
  evidence: {
    step: number;
    url: string | null;
    screenshot_url: string | null;
    page_errors: string[];
    quote: string | null;
  };
  reproduce: string[];
  fix_prompt: string;
  // Steps of the problems the visitor noted that this finding covers, so they are not listed twice.
  covers_steps?: number[];
  // The same symptom seen again, merged into this finding: the earliest step is `evidence`, these are the rest.
  also_seen_at?: { step: number; url: string | null; screenshot_url: string | null; page_errors: string[] }[];
};

export type Run = {
  id: string;
  url: string;
  start_url: string | null;
  has_test_login: boolean;
  access_mode: AccessMode | null;
  first_impression: FirstImpression | null;
  entry: Entry | null;
  findings: Finding[] | null;
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
  "id, url, start_url, has_test_login, access_mode, first_impression, entry, findings, goal, status, outcome, reason, cost_usd, brain_model, created_at, started_at, finished_at";
// The same without the columns added on 2026-10-11 (access_mode, findings), for a database whose schema
// has not been updated yet: the run page still loads, without them.
export const RUN_COLUMNS_BEFORE_FINDINGS = RUN_COLUMNS.replace(" access_mode,", "").replace(" findings,", "");
export const STEP_COLUMNS = "idx, tool, thought, input, result, url, screenshot_path, created_at";
export const FRICTION_COLUMNS = "id, step_idx, kind, severity, expected, happened";
