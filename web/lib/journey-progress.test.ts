import assert from "node:assert/strict";
import { test } from "node:test";

import type { SuggestedJourney } from "./brief-types.ts";
import {
  addRecent,
  listedVerdictKind,
  parseRecent,
  recentSite,
  runForJourney,
  sameGoal,
  timeAgo,
  untestedJourneys,
  type BriefTestRun,
} from "./journey-progress.ts";
import { parseDraft } from "./test-draft.ts";

const ID = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const journey = (goal: string): SuggestedJourney => ({
  goal,
  success: "",
  source_url: "https://a.test",
  basis: "call_to_action",
  basis_text: "",
  claim_to_test: false,
});
const run = (n: number, goal: string, status: BriefTestRun["status"] = "done"): BriefTestRun => ({
  id: ID(n),
  goal,
  status,
  verdict_kind: null,
});

test("goals match ignoring case, spacing and a final full stop", () => {
  assert.ok(sameGoal("Sign up for a trial.", "  sign up  for a TRIAL "));
  assert.ok(!sameGoal("Sign up", "Sign in"));
  assert.ok(!sameGoal("", ""));
});

test("the newest test of a journey wins and tested journeys drop out", () => {
  const runs = [run(2, "Book a demo", "running"), run(1, "book a demo")];
  assert.equal(runForJourney(journey("Book a demo"), runs)?.id, ID(2));
  assert.equal(runForJourney(journey("See pricing"), runs), null);
  assert.deepEqual(
    untestedJourneys([journey("Book a demo"), journey("See pricing")], runs).map((j) => j.goal),
    ["See pricing"],
  );
});

test("listed verdict kind prefers the verdict, then the outcome", () => {
  const base = { verdict_kind: null, outcome: null, bot_check: null } as const;
  assert.equal(listedVerdictKind({ ...base, status: "running" }), null);
  assert.equal(listedVerdictKind({ ...base, status: "done", verdict_kind: "stuck", outcome: "achieved" }), "stuck");
  assert.equal(listedVerdictKind({ ...base, status: "done", verdict_kind: "nonsense", outcome: "achieved" }), "got_through");
  assert.equal(listedVerdictKind({ ...base, status: "done", outcome: "gave_up" }), "stuck");
  assert.equal(listedVerdictKind({ ...base, status: "failed" }), "our_failure");
  assert.equal(listedVerdictKind({ ...base, status: "done", outcome: "blocked", bot_check: { phrase: "x" } }), "bot_check");
});

test("recent runs: odd entries dropped, newest first, ten at most", () => {
  assert.deepEqual(parseRecent(null), []);
  assert.deepEqual(parseRecent("{nope"), []);
  assert.deepEqual(parseRecent(JSON.stringify([{ id: "x", kind: "test", site: "a", at: "2026-01-01" }])), []);
  const good = { id: ID(1), kind: "brief", site: "a.test", at: "2026-10-12T10:00:00Z", goal: "secret" };
  assert.deepEqual(parseRecent(JSON.stringify([good])), [{ id: ID(1), kind: "brief", site: "a.test", at: good.at }]);
  let list = parseRecent(null);
  for (let n = 1; n <= 12; n++) list = addRecent(list, { id: ID(n), kind: "test", site: "a", at: good.at });
  list = addRecent(list, { id: ID(5), kind: "test", site: "a", at: good.at });
  assert.equal(list.length, 10);
  assert.equal(list[0].id, ID(5));
  assert.equal(list.filter((item) => item.id === ID(5)).length, 1);
});

test("the stored site is the host only", () => {
  assert.equal(recentSite("www.shop.test/cart?token=1"), "shop.test");
  assert.equal(recentSite("https://user:pw@app.test/login"), "app.test");
  assert.equal(recentSite("  app.test  "), "app.test");
});

test("time ago", () => {
  const now = Date.parse("2026-10-12T12:00:00Z");
  assert.equal(timeAgo("2026-10-12T11:59:30Z", now), "just now");
  assert.equal(timeAgo("2026-10-12T11:55:00Z", now), "5 min ago");
  assert.equal(timeAgo("2026-10-12T09:00:00Z", now), "3 h ago");
  assert.equal(timeAgo("2026-10-11T12:00:00Z", now), "1 day ago");
});

test("the form draft keeps goal, success and way in only", () => {
  assert.equal(parseDraft(null), null);
  assert.equal(parseDraft("{bad"), null);
  assert.deepEqual(parseDraft(JSON.stringify({ goal: "g", success: "s", access: "account", testPassword: "pw" })), {
    goal: "g",
    success: "s",
    access: "account",
  });
  assert.equal(parseDraft(JSON.stringify({ access: "weird" }))?.access, "public");
});
