import assert from "node:assert/strict";
import { test } from "node:test";

import {
  VERDICT_LABELS,
  feedbackShown,
  feedbackStorageKey,
  findingIds,
  isFindingId,
  isVerdict,
  parseFeedback,
  readStoredVotes,
  storeVote,
} from "./feedback-logic.ts";
import { flagsFrom } from "./report-flags.ts";
import type { Finding } from "./types.ts";

const finding = (extra: Record<string, unknown> = {}) => ({ title: "t", ...extra }) as unknown as Finding;

test("only the three verdicts are accepted", () => {
  for (const verdict of ["useful", "not_a_problem", "fixed"]) assert.equal(isVerdict(verdict), true);
  for (const verdict of ["Useful", "bad", "", null, 3, undefined]) assert.equal(isVerdict(verdict), false);
});

test("a finding id is short plain text", () => {
  for (const id of ["f0", "f12", "a1b2-c3", "step_4.2"]) assert.equal(isFindingId(id), true);
  for (const id of ["", " ", "a b", "x".repeat(65), "<script>", "../x", 5, null]) assert.equal(isFindingId(id), false);
});

test("findings are numbered f0, f1... unless they carry their own id", () => {
  assert.deepEqual(findingIds([finding(), finding({ id: "abc123" }), finding({ id: "bad id!" })]), [
    "f0",
    "abc123",
    "f2",
  ]);
  assert.deepEqual(findingIds(null), []);
  assert.deepEqual(findingIds([]), []);
});

test("a request body is checked for the finding and the verdict", () => {
  assert.deepEqual(parseFeedback({ findingId: "f0", verdict: "fixed" }), {
    ok: true,
    value: { findingId: "f0", verdict: "fixed" },
  });
  const cases: [unknown, string][] = [
    [null, "invalid_request"],
    ["x", "invalid_request"],
    [{ verdict: "fixed" }, "invalid_finding"],
    [{ findingId: "f0" }, "invalid_verdict"],
    [{ findingId: "f0", verdict: "meh" }, "invalid_verdict"],
  ];
  for (const [body, error] of cases) {
    const result = parseFeedback(body);
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.error, error);
  }
});

// A Storage stand-in; `broken` makes every access throw, as a private window or blocked site data can.
function memoryStorage(broken = false) {
  const items = new Map<string, string>();
  return {
    items,
    getItem(key: string) {
      if (broken) throw new Error("SecurityError");
      return items.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      if (broken) throw new Error("QuotaExceededError");
      items.set(key, value);
    },
  };
}

test("the buttons read Useful, Not a real problem and I fixed this", () => {
  assert.deepEqual(VERDICT_LABELS, { useful: "Useful", not_a_problem: "Not a real problem", fixed: "I fixed this" });
});

test("the buttons show only on a finished report with findings that are about the site", () => {
  const base = { status: "done", findings: [finding()], verdict: { kind: "stuck" }, entry: null };
  assert.equal(feedbackShown(base), true);
  assert.equal(feedbackShown({ ...base, verdict: null }), true);
  assert.equal(feedbackShown({ ...base, verdict: { kind: "bot_check" } }), false);
  assert.equal(feedbackShown({ ...base, verdict: { kind: "our_failure" } }), false);
  assert.equal(feedbackShown({ ...base, verdict: null, entry: { bot_check: { phrase: "Verify" } } }), false);
  assert.equal(feedbackShown({ ...base, findings: [] }), false);
  assert.equal(feedbackShown({ ...base, findings: null }), false);
  assert.equal(feedbackShown({ ...base, status: "running" }), false);
  assert.equal(feedbackShown({ ...base, status: "failed" }), false);
});

test("NEXT_PUBLIC_FEEDBACK is on by default and off hides the buttons", () => {
  assert.equal(flagsFrom({}).feedback, true);
  assert.equal(flagsFrom({ feedback: "off" }).feedback, false);
  assert.deepEqual(flagsFrom({ feedback: "off" }), { ...flagsFrom({}), feedback: false });
  assert.equal(flagsFrom({ master: "off" }).feedback, false);
  assert.equal(flagsFrom({}, "?report=basic").feedback, false);
});

test("a vote is remembered per run and a later vote replaces it", () => {
  const storage = memoryStorage();
  storeVote(storage, "run-a", "f0", "useful");
  storeVote(storage, "run-a", "f1", "fixed");
  storeVote(storage, "run-a", "f0", "not_a_problem");
  storeVote(storage, "run-b", "f0", "fixed");
  assert.deepEqual(readStoredVotes(storage, "run-a"), { f0: "not_a_problem", f1: "fixed" });
  assert.deepEqual(readStoredVotes(storage, "run-b"), { f0: "fixed" });
  assert.deepEqual(readStoredVotes(storage, "run-c"), {});
});

test("remembered votes that are damaged or invalid are ignored", () => {
  const storage = memoryStorage();
  storage.items.set(feedbackStorageKey("r"), "{not json");
  assert.deepEqual(readStoredVotes(storage, "r"), {});
  storage.items.set(feedbackStorageKey("r"), JSON.stringify(["useful"]));
  assert.deepEqual(readStoredVotes(storage, "r"), {});
  storage.items.set(feedbackStorageKey("r"), JSON.stringify({ f0: "useful", f1: "great", "bad id": "fixed" }));
  assert.deepEqual(readStoredVotes(storage, "r"), { f0: "useful" });
});

test("storage that is missing or throws never breaks the page", () => {
  assert.deepEqual(readStoredVotes(null, "r"), {});
  assert.deepEqual(readStoredVotes(undefined, "r"), {});
  assert.doesNotThrow(() => storeVote(null, "r", "f0", "useful"));
  const broken = memoryStorage(true);
  assert.deepEqual(readStoredVotes(broken, "r"), {});
  assert.doesNotThrow(() => storeVote(broken, "r", "f0", "useful"));
});
