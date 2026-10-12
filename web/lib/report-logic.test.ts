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
    verdict: null,
    run_facts: null,
    success_condition: null,
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

test("a bot check is not a login block", () => {
  const botCheck = run({
    entry: entry({
      blocked_at_login: true,
      bot_check: { phrase: "Verify you are human", url: "https://shop.example/", title: "Just a moment...", step: 1 },
    }),
  });
  assert.equal(showLoginWallHelp(botCheck, []), false);
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

test("a problem noted at a step where a merged finding saw it again is covered", () => {
  const merged: Finding = {
    ...finding(11),
    also_seen_at: [{ step: 12, url: null, screenshot_url: null, page_errors: [] }],
  };
  const all = [friction(1, 12), friction(2, 9)];
  assert.deepEqual(frictionsNotInFindings(all, [merged]).map((f) => f.id), [2]);
});

test("without findings, every noted problem is shown", () => {
  const all = [friction(1, 13), friction(2, 9)];
  assert.equal(frictionsNotInFindings(all, null).length, 2);
  assert.equal(frictionsNotInFindings(all, []).length, 2);
});

// ---------------------------------------------------------------------------------------- Report v2

import { flagsFrom } from "./report-flags.ts";
import { fixFirst, shortUrl, understanding, withoutPromises } from "./report-logic.ts";
import type { FirstImpression, Verdict } from "./types.ts";

function review(what: "yes" | "partly" | "no", who: "yes" | "partly" | "no", action: "yes" | "partly" | "no"): FirstImpression {
  return {
    what_it_does: { clear: what, summary: "It plans projects." },
    who_its_for: { clear: who, summary: "Nobody is named." },
    main_action: { obvious: action, summary: "A green button." },
    hesitations: ["Pricing is hidden.", "No screenshot.", "Third thing."],
    suggestions: [],
  };
}

test("understanding: clear, partly clear and unclear, with the review's own reasons", () => {
  assert.equal(understanding(review("yes", "yes", "yes"))?.level, "clear");
  assert.equal(understanding(review("yes", "partly", "yes"))?.level, "partly");
  assert.equal(understanding(review("partly", "no", "yes"))?.level, "partly");
  assert.equal(understanding(review("no", "yes", "yes"))?.level, "unclear", "not knowing what it does is unclear");
  assert.equal(understanding(review("yes", "no", "no"))?.level, "unclear", "two of three not clear");
  const partly = understanding(review("yes", "partly", "yes"))!;
  assert.equal(partly.label, "Partly clear");
  assert.deepEqual(partly.reasons, ["Who it is for: Nobody is named.", "Pricing is hidden.", "No screenshot."]);
  assert.equal(understanding(review("yes", "yes", "yes"))!.reasons.length, 2, "only the hesitations, no failed parts");
  assert.equal(understanding(null), null);
});

function verdict(kind: Verdict["kind"]): Verdict {
  return { kind, headline: "h", where_step: null, where_url: null, evidence_quote: "", basis: "observed" };
}

test("what to fix first is the top finding, and nothing for a visit that says nothing about the site", () => {
  const top = finding(3);
  const second = finding(5);
  assert.deepEqual(fixFirst([top, second], verdict("stuck")), { state: "finding", finding: top });
  assert.deepEqual(fixFirst([], verdict("got_through")), { state: "none" });
  assert.deepEqual(fixFirst(null, null), { state: "unavailable" });
  assert.deepEqual(fixFirst([top], verdict("bot_check")), { state: "not_about_site" });
  assert.deepEqual(fixFirst([top], verdict("our_failure")), { state: "not_about_site" });
});

test("every Report v2 section can be switched off, all at once or one at a time", () => {
  const all = flagsFrom({});
  assert.deepEqual(Object.values(all), [true, true, true, true, true, true]);
  assert.equal(flagsFrom({ master: "off" }).verdict, false);
  assert.equal(flagsFrom({ master: "off" }).facts, false);
  assert.deepEqual(flagsFrom({ facts: "false" }), { ...all, facts: false });
  assert.deepEqual(flagsFrom({ answers: "0" }), { ...all, answers: false });
  assert.equal(flagsFrom({ labels: "OFF" }).labels, false);
  assert.equal(flagsFrom({ criteria: "no" }).criteria, false);
  assert.equal(flagsFrom({ success: "hidden" }).success, false);
  assert.equal(flagsFrom({ verdict: "off" }).verdict, false);
  // The address switches everything off for that view, without a rebuild.
  assert.deepEqual(Object.values(flagsFrom({}, "?report=basic")), [false, false, false, false, false, false]);
  assert.equal(flagsFrom({}, "?report=full").answers, true);
});

test("recommendations never show a promised outcome", () => {
  assert.equal(
    withoutPromises("Name the audience in the headline. This will increase sign-ups by 30%."),
    "Name the audience in the headline.",
  );
  assert.equal(withoutPromises("Boost conversion with a bigger button."), "");
  assert.equal(withoutPromises("Add a screenshot above the fold."), "Add a screenshot above the fold.");
});

test("a short address for a page", () => {
  assert.equal(shortUrl("https://shop.test/checkout?x=1"), "shop.test/checkout");
  assert.equal(shortUrl("https://shop.test/"), "shop.test");
  assert.equal(shortUrl(null), "");
});

import { RUN_COLUMNS, RUN_COLUMNS_BEFORE_FINDINGS } from "./types.ts";

test("a database without the newer columns can still be read", () => {
  for (const column of ["access_mode", "findings", "verdict", "run_facts", "success_condition"]) {
    assert.ok(RUN_COLUMNS.split(", ").includes(column), `${column} is selected when the schema is current`);
    assert.ok(!RUN_COLUMNS_BEFORE_FINDINGS.split(", ").includes(column), `${column} is left out for an older one`);
  }
  assert.ok(RUN_COLUMNS_BEFORE_FINDINGS.split(", ").includes("first_impression"));
  assert.ok(RUN_COLUMNS_BEFORE_FINDINGS.split(", ").includes("outcome"));
});
