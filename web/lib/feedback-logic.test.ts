import assert from "node:assert/strict";
import { test } from "node:test";

import { findingIds, isFindingId, isVerdict, parseFeedback } from "./feedback-logic.ts";
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
