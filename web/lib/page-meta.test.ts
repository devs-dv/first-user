import assert from "node:assert/strict";
import { test } from "node:test";

import { briefMeta, reportMeta, type ReportMetaRun } from "./page-meta.ts";
import type { Verdict } from "./types.ts";

function run(overrides: Partial<ReportMetaRun> = {}): ReportMetaRun {
  return { url: "https://www.example.com/", status: "done", outcome: "achieved", verdict: null, entry: null, ...overrides };
}

test("a report's title is the site and the verdict's own headline", () => {
  const verdict: Verdict = {
    kind: "stuck",
    headline: "A first-time visitor got stuck on /cart",
    where_step: 4,
    where_url: null,
    evidence_quote: "",
    basis: "observed",
  };
  const meta = reportMeta(run({ outcome: "blocked", verdict }));
  assert.equal(meta.title, "example.com: A first-time visitor got stuck on /cart");
  assert.match(meta.description, /^Verdict: Stuck\. A first-time visitor got stuck on \/cart\. First User tried example\.com/);
});

test("an older run without a verdict gets the same words from its outcome", () => {
  assert.equal(reportMeta(run()).title, "example.com: A first-time visitor got through");
  assert.match(reportMeta(run()).description, /^Verdict: Got through\./);
  assert.equal(reportMeta(run({ status: "failed", outcome: null })).title.startsWith("example.com: The visit failed on our side"), true);
});

test("a run under way, or one that cannot be read, gets a plain title", () => {
  assert.equal(reportMeta(run({ status: "running", outcome: null })).title, "example.com: visit in progress");
  assert.equal(reportMeta(null).title, "Visit report");
});

test("a brief's title is the site and 'brief'", () => {
  assert.equal(briefMeta("https://saucedemo.com/").title, "saucedemo.com brief");
  assert.equal(briefMeta(null).title, "Product brief");
});
