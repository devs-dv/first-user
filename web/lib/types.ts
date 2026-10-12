// Shapes returned by GET /api/runs/[id]. Shared by the API route and the run page.

import type { HiddenText } from "./hidden-text.ts";

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
  // The problem is observed in the run; the fix is our recommendation. Absent on older findings.
  basis?: "observed";
  fix_basis?: "recommendation";
  // Three to five checks a person can make by looking at the page after the change.
  acceptance_criteria?: string[];
  // The same symptom seen again, merged into this finding: the earliest step is `evidence`, these are the rest.
  also_seen_at?: { step: number; url: string | null; screenshot_url: string | null; page_errors: string[] }[];
};

// What a statement in the report rests on: the run record, the independent check, or our suggestion.
export type Basis = "observed" | "verified" | "recommendation";

export type VerdictKind = "got_through" | "unconfirmed" | "stuck" | "login_wall" | "bot_check" | "our_failure";

// One verdict per run (worker/verdict.py).
export type Verdict = {
  kind: VerdictKind;
  headline: string;
  where_step: number | null;
  where_url: string | null;
  evidence_quote: string;
  basis: "observed" | "verified";
  detail?: string;
  ways_in?: string[];
};

// How the report was made (worker/run_facts.py): counted from the run, not written by a model.
export type RunFacts = {
  steps_taken: number;
  recoveries: { step: number; rung: string; how: string; instruction: string }[];
  own_issues: { step: number | null; instruction: string; reason: string | null }[];
  page_reloads: number;
  page_errors: string[];
  page_error_count: number;
  verifier: { verdict: string | null; quote: string } | null;
  success_condition: string | null;
  checked_without_success_condition: boolean;
  cost_usd: number;
  duration_seconds: number;
  agent_version?: string;
  worker_id?: string;
  trace_id?: string | null;
};

// Check again (worker/retest.py): what happened to each finding of the original run.
export type RetestLabel = "fixed" | "still_present" | "not_reached" | "inconclusive" | "new";

export type RetestItem = {
  finding_index?: number;
  title: string;
  kind?: string;
  severity?: string;
  original_step?: number | null;
  original_url?: string | null;
  label: RetestLabel;
  // Which pass produced the label: the independent visit, or the guided follow-up along the original route.
  pass?: "independent" | "guided" | null;
  // A step of this (the retest's) report.
  evidence_step: number | null;
  reason?: string;
  basis?: "observed";
};

export type RetestVerdictSide = {
  kind: VerdictKind;
  headline: string;
  where_step: number | null;
  where_url: string | null;
} | null;

export type RetestResult = {
  original_run_id?: string;
  labels: RetestItem[];
  new: RetestItem[];
  counts?: Record<string, number>;
  verdict?: { before: RetestVerdictSide; after: RetestVerdictSide; change: string; summary: string };
  fixed_means?: string;
  guided?: { attempted: number; followed: number };
  error?: string;
};

export type Run = {
  id: string;
  url: string;
  start_url: string | null;
  has_test_login: boolean;
  access_mode: AccessMode | null;
  first_impression: FirstImpression | null;
  // Evidence that the page hid instructions aimed at AI agents (worker/hidden_text.py): where and how, never the
  // text. Read from the run's result only for this field. See lib/hidden-text.ts for what the page shows of it.
  hidden_text?: HiddenText;
  entry: Entry | null;
  findings: Finding[] | null;
  verdict: Verdict | null;
  run_facts: RunFacts | null;
  success_condition: string | null;
  retest_of: string | null;
  retest: RetestResult | null;
  // The product brief this test was started from, if any.
  brief_run_id?: string | null;
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

// The original of a retest, and the latest check of a run (either may be absent).
export type RunLink = { id: string; status?: string; verdict?: Verdict | null; outcome?: Outcome | null };

export type RunDetails = {
  run: Run;
  steps: Step[];
  frictions: Friction[];
  original?: RunLink | null;
  latest_retest?: RunLink | null;
};

export type ApiError = { error: string; message: string };

// Never includes the test login: it lives in run_secrets, which the web app never reads. Of the run's raw
// result, only the hidden-text evidence is read.
// One string literal, so supabase-js can infer the row type from it.
export const RUN_COLUMNS =
  "id, url, start_url, has_test_login, access_mode, first_impression, hidden_text:result->hidden_text, entry, findings, verdict, run_facts, success_condition, retest_of, retest, brief_run_id, goal, status, outcome, reason, cost_usd, brain_model, created_at, started_at, finished_at";
// The same without the columns added on 2026-10-11 (access_mode, findings), for a database whose schema
// has not been updated yet: the run page still loads, without them.
export const RUN_COLUMNS_BEFORE_FINDINGS = RUN_COLUMNS.replace(" access_mode,", "")
  .replace(" findings,", "")
  .replace(" verdict,", "")
  .replace(" run_facts,", "")
  .replace(" success_condition,", "")
  .replace(" retest_of,", "")
  .replace(" retest,", "")
  .replace(" brief_run_id,", "");
export const STEP_COLUMNS = "idx, tool, thought, input, result, url, screenshot_path, created_at";
export const FRICTION_COLUMNS = "id, step_idx, kind, severity, expected, happened";
