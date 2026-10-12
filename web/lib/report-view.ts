// Rules of the redesigned report page that do not need React, so they can be tested with Node alone
// (npm test). Types only are imported: no runtime dependencies.

import type { Outcome, Run, Step, VerdictKind } from "./types.ts";

// ---------------------------------------------------------------------------------------------------
// The verdict hero's six states.

// Older runs (from before Report v2, or with the verdict switched off) have only an outcome. The hero still
// needs one of the six states for its colour and label; this reads it from what the run recorded.
export function verdictKindOf(
  run: Pick<Run, "status" | "outcome" | "verdict" | "entry">,
  loginWall: boolean,
  useVerdict = true,
): VerdictKind {
  if (useVerdict && run.verdict?.kind) return run.verdict.kind;
  if (run.status === "failed") return "our_failure";
  if (run.entry?.bot_check) return "bot_check";
  const outcome: Outcome = run.outcome ?? "error";
  switch (outcome) {
    case "achieved":
      return "got_through";
    case "achieved_unconfirmed":
    case "unverified":
      return "unconfirmed";
    case "blocked":
      return loginWall ? "login_wall" : "stuck";
    case "error":
      return "our_failure";
    default:
      return "stuck";
  }
}

// ---------------------------------------------------------------------------------------------------
// The fix prompt, split into the parts the worker writes (worker/report_writer.py build_fix_prompt):
// "Fix: <title>", then blocks headed "Observed issue ...", "Expected behaviour", "What to change",
// "Constraints", "Acceptance criteria ...", "Retest". A prompt from before that format is one part.

export type FixPart = { heading: string; kind: "text" | "criteria" | "retest"; lines: string[] };

const HEADINGS: [RegExp, string, FixPart["kind"]][] = [
  [/^observed issue\b/i, "Observed issue", "text"],
  [/^expected behaviou?r$/i, "Expected behaviour", "text"],
  [/^what to change$/i, "What to change", "text"],
  [/^constraints$/i, "Constraints", "text"],
  [/^acceptance criteria\b/i, "Acceptance criteria", "criteria"],
  [/^retest$/i, "Retest instruction", "retest"],
];

export function fixPromptParts(prompt: string): FixPart[] {
  const text = (prompt ?? "").replace(/\r\n/g, "\n").trim();
  if (!text) return [];
  const lines = text.split("\n");
  if (!/^fix:/i.test(lines[0] ?? "")) {
    return [{ heading: "Fix prompt", kind: "text", lines: text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean) }];
  }
  const parts: FixPart[] = [];
  let current: FixPart | null = null;
  for (const raw of lines.slice(1)) {
    const line = raw.trimEnd();
    const heading = HEADINGS.find(([pattern]) => pattern.test(line.trim()));
    if (heading) {
      current = { heading: heading[1], kind: heading[2], lines: [] };
      parts.push(current);
      continue;
    }
    if (!line.trim()) continue;
    if (!current) {
      current = { heading: "Fix prompt", kind: "text", lines: [] };
      parts.push(current);
    }
    current.lines.push(line);
  }
  // List markers are the page's job: "- x" and "1. x" become plain items, keeping nested steps indented.
  return parts
    .map((part) => ({
      ...part,
      lines: part.lines.map((line) =>
        part.kind === "criteria" ? line.trim().replace(/^(\d+\.|-)\s+/, "") : line.replace(/^- /, ""),
      ),
    }))
    .filter((part) => part.lines.length > 0);
}

// ---------------------------------------------------------------------------------------------------
// Steps, in words.

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function describeAction(step: Pick<Step, "tool" | "input">): string {
  const input = step.input ?? {};
  switch (step.tool) {
    case "look":
      return "Looked at the page";
    case "do":
      return `Tried to ${text(input.instruction) || "act on the page"}`;
    case "scroll":
      return `Scrolled ${text(input.direction) || "the page"}`;
    case "go_back":
      return "Went back";
    case "note_friction":
      return "Noted a problem";
    case "finish":
      return "Ended the visit";
    case "sign_in":
      return "Signed in with the test login";
    case "sign_up":
      return "Signed up with a test account";
    default:
      return step.tool;
  }
}

export type StepTone = "done" | "retry" | "problem" | "ours" | "end" | "blocked" | "error";
export type StepStatus = { label: string; tone: StepTone };

// Which try of the worker's recovery ladder changed the page (worker/tools.py do()): a is the first.
const RUNG_TRY: Record<string, number> = { a: 1, b: 2, c: 3, d: 4 };

function pageErrorCount(result: Record<string, unknown>): number {
  const count = result.page_error_count;
  if (typeof count === "number") return count;
  return Array.isArray(result.page_errors) ? result.page_errors.length : 0;
}

// The coloured result on each step card of "The whole run".
export function stepStatus(step: Pick<Step, "tool" | "result">): StepStatus {
  const result = step.result ?? {};
  if (result.bot_check) return { label: "Bot check", tone: "blocked" };
  if (result.error) return { label: "Tool error", tone: "ours" };
  switch (step.tool) {
    case "do": {
      if (pageErrorCount(result) > 0) return { label: "Page error", tone: "error" };
      if (!result.success) return { label: "No effect", tone: "ours" };
      const attempt = RUNG_TRY[text(result.rung)] ?? 1;
      return attempt > 1 ? { label: `Needed recovery on try ${attempt}`, tone: "retry" } : { label: "Worked", tone: "done" };
    }
    case "note_friction":
      return { label: "Noted a problem", tone: "problem" };
    case "finish":
      return { label: "Finished", tone: "end" };
    default:
      return { label: "Worked", tone: "done" };
  }
}

export type StepKind = "look" | "click" | "type" | "scroll" | "back" | "note" | "finish" | "login";

// The small icon on each step card.
export function stepKind(step: Pick<Step, "tool" | "input">): StepKind {
  switch (step.tool) {
    case "look":
      return "look";
    case "scroll":
      return "scroll";
    case "go_back":
      return "back";
    case "note_friction":
      return "note";
    case "finish":
      return "finish";
    case "sign_in":
    case "sign_up":
      return "login";
    default:
      return /^\s*(type|enter|fill|write|input|select)\b/i.test(text(step.input?.instruction)) ? "type" : "click";
  }
}

export type StepMark = "Finding" | "Recovery" | "Page error" | "Final step";

// Steps that matter get an accent border and a label: one a finding points at, a recovery, a page error, the last.
export function stepMarks(step: Pick<Step, "idx" | "tool" | "result">, findingSteps: Set<number>, lastIdx: number): StepMark[] {
  const marks: StepMark[] = [];
  const result = step.result ?? {};
  if (findingSteps.has(step.idx)) marks.push("Finding");
  if (step.tool === "do" && result.success && (RUNG_TRY[text(result.rung)] ?? 1) > 1) marks.push("Recovery");
  if (pageErrorCount(result) > 0) marks.push("Page error");
  if (step.idx === lastIdx) marks.push("Final step");
  return marks;
}

// ---------------------------------------------------------------------------------------------------
// A run on its way: which phase it is in, from what has been saved so far. Steps are saved as they happen; the
// first impression is saved once the page is read; the independent check and the report come after the
// visitor's last step.

export const LIVE_PHASES = [
  "Queued",
  "Starting a browser",
  "Understanding the page",
  "Exploring",
  "Verifying",
  "Writing the report",
] as const;
export const MAX_STEPS = 20;

// One calm line per phase.
export const PHASE_LINES = [
  "Waiting for a free browser",
  "Opening your site like a first-time visitor",
  "Reading the page the way a newcomer would",
  "Trying the goal, one action at a time",
  "Checking the final page independently",
  "Writing up what happened",
] as const;

export type LiveState = {
  queued: boolean;
  phase: number; // index into LIVE_PHASES
  stepCount: number;
  action: string;
  screenshot: { url: string; step: number; pageUrl: string | null } | null;
  pageUrl: string | null;
};

export function liveState(run: Pick<Run, "status" | "first_impression">, steps: Step[]): LiveState {
  const queued = run.status === "queued";
  const last = steps[steps.length - 1];
  const finish = steps.find((step) => step.tool === "finish");
  const acted = steps.some((step) => step.tool !== "look");
  let phase: number;
  if (queued) phase = 0;
  else if (finish) phase = text(finish.input?.outcome) === "achieved" ? 4 : 5;
  else if (acted) phase = 3;
  else if (steps.length > 0 || run.first_impression) phase = 2;
  else phase = 1;
  const shot = [...steps].reverse().find((step) => isHttpUrl(step.screenshot_path));
  const pageUrl = [...steps].reverse().find((step) => step.url)?.url ?? null;
  const action = phase === 3 && last ? describeAction(last) : PHASE_LINES[phase];
  return {
    queued,
    phase,
    stepCount: steps.length,
    action,
    screenshot: shot ? { url: shot.screenshot_path as string, step: shot.idx, pageUrl: shot.url } : null,
    pageUrl,
  };
}

export function isHttpUrl(value: string | null | undefined): value is string {
  return !!value && /^https?:\/\//i.test(value);
}

// The screenshot a step card shows: its own, else the nearest earlier one. The worker links a screenshot only to
// do() steps; look() uploads one without linking it and finish() takes none, so those show the page as it was
// left by the step before. `from` is the step the screenshot belongs to.
export function stepShot(steps: Step[], idx: number): { url: string; from: number } | null {
  let found: Step | null = null;
  for (const step of steps) {
    if (step.idx > idx) break;
    if (isHttpUrl(step.screenshot_path)) found = step;
  }
  return found ? { url: found.screenshot_path as string, from: found.idx } : null;
}

// ---------------------------------------------------------------------------------------------------
// How long the run took: one source for every place the report shows it. The run facts' own count when there
// is one, otherwise the run's start and finish times.

export function runSeconds(run: Pick<Run, "run_facts" | "started_at" | "finished_at">): number | null {
  const counted = run.run_facts?.duration_seconds;
  if (typeof counted === "number" && Number.isFinite(counted)) return Math.max(0, Math.round(counted));
  if (!run.started_at || !run.finished_at) return null;
  const seconds = (Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000;
  return Number.isFinite(seconds) ? Math.max(0, Math.round(seconds)) : null;
}

export function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "—";
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

// ---------------------------------------------------------------------------------------------------
// Sharing.

// The default post text, worded for the verdict: a run that got through does not say it got stuck.
export function shareText(site: string, link: string, kind: VerdictKind): string {
  const middle =
    kind === "got_through"
      ? "like a first-time customer and got through. Here's the report:"
      : kind === "stuck"
        ? "like a first-time customer. Here's where it got stuck:"
        : "like a first-time customer. Here's what it found:";
  return `First User just tried ${site} ${middle} ${link} #neatHack via @devsdv_`;
}

export function shareLinks(textToShare: string): { x: string; linkedin: string } {
  const encoded = encodeURIComponent(textToShare);
  return {
    x: `https://x.com/intent/post?text=${encoded}`,
    linkedin: `https://www.linkedin.com/feed/?shareActive=true&text=${encoded}`,
  };
}

// The host of an address, for headings ("saucedemo.com"), without "www.".
export function siteName(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function pathOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return "";
  }
}
