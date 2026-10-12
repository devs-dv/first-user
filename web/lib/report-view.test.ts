import assert from "node:assert/strict";
import { test } from "node:test";

import {
  fixPromptParts,
  liveState,
  formatSeconds,
  runSeconds,
  shareLinks,
  shareText,
  stepKind,
  stepMarks,
  stepStatus,
  verdictKindOf,
} from "./report-view.ts";
import type { Run, Step, Verdict } from "./types.ts";

type VerdictRun = Pick<Run, "status" | "outcome" | "verdict" | "entry">;

function verdictRun(overrides: Partial<VerdictRun> = {}): VerdictRun {
  return { status: "done", outcome: "achieved", verdict: null, entry: null, ...overrides };
}

function step(idx: number, tool: string, extra: Partial<Step> = {}): Step {
  return {
    idx,
    tool,
    thought: null,
    input: {},
    result: {},
    url: "https://example.com/",
    screenshot_path: null,
    created_at: "2026-10-12T00:00:00Z",
    ...extra,
  };
}

test("the verdict's own kind wins when there is one", () => {
  const verdict: Verdict = { kind: "unconfirmed", headline: "h", where_step: null, where_url: null, evidence_quote: "", basis: "observed" };
  assert.equal(verdictKindOf(verdictRun({ verdict }), false), "unconfirmed");
  // With the verdict switched off, the outcome decides.
  assert.equal(verdictKindOf(verdictRun({ verdict }), false, false), "got_through");
});

test("older runs get one of the six states from their outcome", () => {
  assert.equal(verdictKindOf(verdictRun({ outcome: "achieved" }), false), "got_through");
  assert.equal(verdictKindOf(verdictRun({ outcome: "achieved_unconfirmed" }), false), "unconfirmed");
  assert.equal(verdictKindOf(verdictRun({ outcome: "unverified" }), false), "unconfirmed");
  assert.equal(verdictKindOf(verdictRun({ outcome: "gave_up" }), false), "stuck");
  assert.equal(verdictKindOf(verdictRun({ outcome: "max_steps" }), false), "stuck");
  assert.equal(verdictKindOf(verdictRun({ outcome: "blocked" }), false), "stuck");
  assert.equal(verdictKindOf(verdictRun({ outcome: "blocked" }), true), "login_wall");
  assert.equal(verdictKindOf(verdictRun({ outcome: "error" }), false), "our_failure");
  assert.equal(verdictKindOf(verdictRun({ status: "failed", outcome: null }), false), "our_failure");
  const bot = { phrase: "Verify you are human", url: "https://x.test/", title: "", step: 1 };
  assert.equal(
    verdictKindOf(verdictRun({ outcome: "blocked", entry: { bot_check: bot } as Run["entry"] }), true),
    "bot_check",
  );
});

test("a structured fix prompt splits into its parts", () => {
  const prompt = [
    "Fix: Create project does nothing",
    "",
    "Observed issue (from an automated first-visit test)",
    "- What happened: the form stayed.",
    "- Steps to reproduce:",
    "  1. Open the page.",
    "",
    "Expected behaviour",
    "The project opens.",
    "",
    "What to change",
    "Keep the input on failure.",
    "",
    "Constraints",
    "- Do not change the URL format.",
    "",
    "Acceptance criteria (each one can be checked by looking at the page)",
    "1. One click creates the project.",
    "2. It appears in the dashboard.",
    "",
    "Retest",
    "Run the same goal again.",
  ].join("\n");
  const parts = fixPromptParts(prompt);
  assert.deepEqual(
    parts.map((part) => part.heading),
    ["Observed issue", "Expected behaviour", "What to change", "Constraints", "Acceptance criteria", "Retest instruction"],
  );
  assert.deepEqual(parts[0].lines, ["What happened: the form stayed.", "Steps to reproduce:", "  1. Open the page."]);
  assert.deepEqual(parts[4].lines, ["One click creates the project.", "It appears in the dashboard."]);
  assert.equal(parts[4].kind, "criteria");
  assert.equal(parts[5].kind, "retest");
});

test("an older free-text fix prompt is one part, by paragraph", () => {
  const parts = fixPromptParts("Find why the field is empty.\n\nContext, from an automated first-visit test.");
  assert.equal(parts.length, 1);
  assert.equal(parts[0].heading, "Fix prompt");
  assert.deepEqual(parts[0].lines, ["Find why the field is empty.", "Context, from an automated first-visit test."]);
  assert.deepEqual(fixPromptParts(""), []);
});

test("each step gets a coloured result", () => {
  assert.deepEqual(stepStatus(step(1, "do", { result: { success: true, rung: "a" } })), { label: "Worked", tone: "done" });
  assert.equal(stepStatus(step(1, "do", { result: { success: true, rung: "c" } })).label, "Needed recovery on try 3");
  assert.equal(stepStatus(step(1, "do", { result: { success: false } })).label, "No effect");
  assert.equal(stepStatus(step(1, "do", { result: { success: false, page_error_count: 2 } })).label, "Page error");
  assert.equal(stepStatus(step(1, "note_friction")).tone, "problem");
  assert.equal(stepStatus(step(1, "finish")).label, "Finished");
  assert.equal(stepStatus(step(1, "look", { result: { bot_check: true } })).label, "Bot check");
});

test("each step gets an icon for its kind of action", () => {
  assert.equal(stepKind(step(1, "look")), "look");
  assert.equal(stepKind(step(1, "do", { input: { instruction: "Type 'Jane' into First Name" } })), "type");
  assert.equal(stepKind(step(1, "do", { input: { instruction: "Click the Login button" } })), "click");
  assert.equal(stepKind(step(1, "scroll")), "scroll");
  assert.equal(stepKind(step(1, "finish")), "finish");
});

test("findings, recoveries, page errors and the last step are marked", () => {
  const findings = new Set([4]);
  assert.deepEqual(stepMarks(step(4, "do", { result: { success: true, rung: "a" } }), findings, 9), ["Finding"]);
  assert.deepEqual(stepMarks(step(5, "do", { result: { success: true, rung: "b" } }), findings, 9), ["Recovery"]);
  assert.deepEqual(stepMarks(step(6, "do", { result: { success: false, page_error_count: 1 } }), findings, 9), ["Page error"]);
  assert.deepEqual(stepMarks(step(9, "finish"), findings, 9), ["Final step"]);
  assert.deepEqual(stepMarks(step(2, "look"), findings, 9), []);
});

test("a live run's phase comes from what has been saved", () => {
  const live = (status: Run["status"], steps: Step[], first_impression: Run["first_impression"] = null) =>
    liveState({ status, first_impression }, steps);
  assert.equal(live("queued", []).phase, 0);
  assert.equal(live("queued", []).action, "Waiting for a free browser");
  assert.equal(live("running", []).phase, 1);
  assert.equal(live("running", []).action, "Opening your site like a first-time visitor");
  assert.equal(live("running", [step(1, "look")]).phase, 2);
  const exploring = live("running", [
    step(1, "look"),
    step(2, "do", { input: { instruction: "click Login" }, screenshot_path: "https://cdn.test/2.png" }),
  ]);
  assert.equal(exploring.phase, 3);
  assert.equal(exploring.stepCount, 2);
  assert.equal(exploring.action, "Tried to click Login");
  assert.equal(exploring.screenshot?.step, 2);
  const achieved = [step(1, "do"), step(2, "finish", { input: { outcome: "achieved", reason: "r" } })];
  assert.equal(live("running", achieved).phase, 4);
  const blocked = [step(1, "do"), step(2, "finish", { input: { outcome: "blocked", reason: "r" } })];
  assert.equal(live("running", blocked).phase, 5);
  // A screenshot that is not an http(s) address is never used.
  assert.equal(live("running", [step(1, "do", { screenshot_path: "javascript:alert(1)" })]).screenshot, null);
});

test("the share text matches the verdict and carries the site and the report link", () => {
  const link = "https://first.user/run/abc";
  assert.equal(
    shareText("saucedemo.com", link, "got_through"),
    "First User just tried saucedemo.com like a first-time customer and got through. Here's the report: https://first.user/run/abc #neatHack via @devsdv_",
  );
  const textToShare = shareText("saucedemo.com", link, "stuck");
  assert.equal(
    textToShare,
    "First User just tried saucedemo.com like a first-time customer. Here's where it got stuck: https://first.user/run/abc #neatHack via @devsdv_",
  );
  for (const kind of ["unconfirmed", "login_wall", "bot_check", "our_failure"] as const) {
    assert.equal(
      shareText("saucedemo.com", link, kind),
      "First User just tried saucedemo.com like a first-time customer. Here's what it found: https://first.user/run/abc #neatHack via @devsdv_",
    );
  }
  const links = shareLinks(textToShare);
  assert.ok(links.x.startsWith("https://x.com/intent/post?text="));
  assert.ok(links.x.includes(encodeURIComponent("#neatHack")));
  assert.ok(links.linkedin.startsWith("https://www.linkedin.com/"));
});

test("the header and the run facts show one duration from one source", () => {
  const times = { started_at: "2026-10-12T10:00:00Z", finished_at: "2026-10-12T10:01:52Z" };
  const facts = { duration_seconds: 108.4 } as Run["run_facts"];
  // The run facts' own count wins over the timestamps, so both places show 1m 48s, never 1m 52s in one of them.
  assert.equal(runSeconds({ ...times, run_facts: facts }), 108);
  assert.equal(formatSeconds(runSeconds({ ...times, run_facts: facts })), "1m 48s");
  assert.equal(formatSeconds(runSeconds({ ...times, run_facts: null })), "1m 52s");
  assert.equal(runSeconds({ started_at: null, finished_at: null, run_facts: null }), null);
  assert.equal(formatSeconds(null), "—");
  assert.equal(formatSeconds(9), "9s");
});
