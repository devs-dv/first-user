import assert from "node:assert/strict";
import { test } from "node:test";

import { frictionsNotInFindings, gotPastLogin, showLoginWallHelp } from "./report-logic.ts";
import type { Entry, Finding, Friction, Run, Step } from "./types.ts";

function entry(overrides: Partial<Entry> = {}): Entry {
  return {
    start_link: null,
    test_login: "not_provided",
    self_signup: "not_used",
    third_party_options: [],
    created_account_email: null,
    blocked_at_login: false,
    ...overrides,
  };
}

function run(overrides: Partial<Run> = {}): Run {
  return {
    id: "r",
    url: "https://www.saucedemo.com/",
    start_url: null,
    has_test_login: false,
    access_mode: "public",
    first_impression: null,
    entry: entry(),
    findings: null,
    goal: "g",
    status: "done",
    outcome: "blocked",
    reason: "x",
    cost_usd: null,
    brain_model: null,
    created_at: "",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function step(idx: number, url: string): Step {
  return { idx, tool: "look", thought: null, input: null, result: null, url, screenshot_path: null, created_at: "" };
}

const BLOCKED_AT_CHECKOUT = [
  step(1, "https://www.saucedemo.com/"),
  step(4, "https://www.saucedemo.com/inventory.html"),
  step(8, "https://www.saucedemo.com/checkout-step-one.html"),
];

test("a run blocked at checkout after the page's own login was accepted shows no login help", () => {
  // The stored run 91e44505: blocked_at_login was true because the reason mentioned a password.
  const stored = run({ entry: entry({ page_login: "shown_on_page", blocked_at_login: true }) });
  assert.equal(gotPastLogin(stored, BLOCKED_AT_CHECKOUT), true);
  assert.equal(showLoginWallHelp(stored, BLOCKED_AT_CHECKOUT), false);
  // The worker's own flag, for runs from now on.
  const flagged = run({ entry: entry({ page_login: "shown_on_page", page_login_worked: true, blocked_at_login: true }) });
  assert.equal(showLoginWallHelp(flagged, [step(1, "https://www.saucedemo.com/")]), false);
});

test("a login that did not work still shows the help", () => {
  const stuck = run({ entry: entry({ page_login: "shown_on_page", blocked_at_login: true }) });
  assert.equal(showLoginWallHelp(stuck, [step(1, "https://www.saucedemo.com/"), step(3, "https://www.saucedemo.com/")]), true);
  const rejected = run({ entry: entry({ page_login: "shown_on_page", page_login_worked: false, blocked_at_login: true }) });
  assert.equal(showLoginWallHelp(rejected, BLOCKED_AT_CHECKOUT), true, "the worker said it did not work");
});

test("signed in with a test account or an account the visitor made is not a login block", () => {
  for (const overrides of [{ test_login: "used" as const }, { self_signup: "used" as const }]) {
    const r = run({ entry: entry({ ...overrides, blocked_at_login: true }) });
    assert.equal(showLoginWallHelp(r, []), false);
  }
});

test("a block at the login itself shows the help, and only for blocked runs", () => {
  const atLogin = run({ entry: entry({ blocked_at_login: true, test_login: "failed" }) });
  assert.equal(showLoginWallHelp(atLogin, []), true);
  assert.equal(showLoginWallHelp(run({ outcome: "achieved", entry: entry({ blocked_at_login: true }) }), []), false);
  assert.equal(showLoginWallHelp(run({ entry: entry({ blocked_at_login: false }) }), []), false);
  assert.equal(showLoginWallHelp(run({ entry: null }), []), false);
});

function friction(id: number, stepIdx: number | null): Friction {
  return { id, step_idx: stepIdx, kind: "site", severity: "medium", expected: "e", happened: "h" };
}

function finding(step: number, covers?: number[]): Finding {
  return {
    title: "t",
    severity: "high",
    kind: "site_problem",
    expected: "e",
    happened: "h",
    evidence: { step, url: null, screenshot_url: null, page_errors: [], quote: null },
    reproduce: [],
    fix_prompt: "p",
    ...(covers ? { covers_steps: covers } : {}),
  };
}

test("noted problems that became findings are not repeated", () => {
  const all = [friction(1, 13), friction(2, 9), friction(3, null)];
  assert.deepEqual(frictionsNotInFindings(all, [finding(12, [13])]).map((f) => f.id), [2, 3]);
});

test("a problem noted at a finding's own step counts as covered", () => {
  const all = [friction(1, 12), friction(2, 9)];
  assert.deepEqual(frictionsNotInFindings(all, [finding(12)]).map((f) => f.id), [2]);
});

test("without findings, every noted problem is shown", () => {
  const all = [friction(1, 13), friction(2, 9)];
  assert.equal(frictionsNotInFindings(all, null).length, 2);
  assert.equal(frictionsNotInFindings(all, []).length, 2);
});
