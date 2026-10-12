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

export type StepTone = "done" | "retry" | "problem" | "ours" | "end" | "blocked";
export type StepStatus = { label: string; tone: StepTone };

// The chip on each step card of "The whole run".
export function stepStatus(step: Pick<Step, "tool" | "result">): StepStatus {
  const result = step.result ?? {};
  if (result.bot_check) return { label: "Bot check", tone: "blocked" };
  if (result.error) return { label: "Tool error", tone: "ours" };
  switch (step.tool) {
    case "do":
      if (!result.success) return { label: "No effect", tone: "ours" };
      return text(result.rung) && text(result.rung) !== "a" ? { label: "Needed a retry", tone: "retry" } : { label: "Done", tone: "done" };
    case "note_friction":
      return { label: "Noted a problem", tone: "problem" };
    case "finish":
      return { label: "Finished", tone: "end" };
    default:
      return { label: "Done", tone: "done" };
  }
}

// ---------------------------------------------------------------------------------------------------
// A run in progress: which of the four phases it is in, from what has been saved so far. Steps are saved
// as they happen; the independent check and the report are written after the visitor's last step.

export const LIVE_PHASES = ["Understanding the page", "Exploring", "Verifying", "Writing the report"] as const;
export const MAX_STEPS = 20;

export type LiveState = {
  queued: boolean;
  phase: number; // index into LIVE_PHASES; -1 while queued
  stepCount: number;
  action: string;
  screenshot: { url: string; step: number; pageUrl: string | null } | null;
  pageUrl: string | null;
};

export function liveState(run: Pick<Run, "status">, steps: Step[]): LiveState {
  const queued = run.status === "queued";
  const last = steps[steps.length - 1];
  const finish = steps.find((step) => step.tool === "finish");
  const acted = steps.some((step) => step.tool !== "look");
  let phase = -1;
  if (!queued) {
    if (finish) phase = text(finish.input?.outcome) === "achieved" ? 2 : 3;
    else phase = acted ? 1 : 0;
  }
  const shot = [...steps].reverse().find((step) => isHttpUrl(step.screenshot_path));
  const pageUrl = [...steps].reverse().find((step) => step.url)?.url ?? null;
  let action: string;
  if (queued) action = "Waiting for a free browser";
  else if (!last) action = "Opening the page and reading it";
  else if (finish) action = phase === 2 ? "Checking the final page independently" : "Writing the report";
  else action = describeAction(last);
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

// ---------------------------------------------------------------------------------------------------
// Sharing.

export function shareText(site: string, link: string): string {
  return `First User just tried ${site} like a first-time customer. Here's where it got stuck: ${link} #neatHack via @devsdv_`;
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
