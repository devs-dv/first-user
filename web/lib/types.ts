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

export type Run = {
  id: string;
  url: string;
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

export const RUN_COLUMNS =
  "id, url, goal, status, outcome, reason, cost_usd, brain_model, created_at, started_at, finished_at";
export const STEP_COLUMNS = "idx, tool, thought, input, result, url, screenshot_path, created_at";
export const FRICTION_COLUMNS = "id, step_idx, kind, severity, expected, happened";
