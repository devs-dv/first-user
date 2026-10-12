import assert from "node:assert/strict";
import { test } from "node:test";

import { founderFlagFrom } from "./founder-flag.ts";
import { FOUNDER_NOTE, TRACTION_LABEL, isFounderBrief, isFounderFailure } from "./founder-types.ts";

test("the founder brief is off unless the switch is on", () => {
  for (const value of [undefined, "", "off", "0", "false", "no", "maybe"]) assert.equal(founderFlagFrom(value), false);
  for (const value of ["on", "1", "true", "YES", " enabled "]) assert.equal(founderFlagFrom(value), true);
});

test("the fixed note and the traction label are exactly the agreed words", () => {
  assert.equal(
    FOUNDER_NOTE,
    "Built only from the public website. It cannot judge the team, real demand, revenue or retention.",
  );
  assert.equal(TRACTION_LABEL, "Stated by the company, not verified");
});

test("a founder brief and a failure are told apart", () => {
  assert.equal(isFounderBrief({ kind: "founder_brief", readiness: [] }), true);
  assert.equal(isFounderBrief({ kind: "founder_brief" }), false);
  assert.equal(isFounderBrief(null), false);
  assert.equal(isFounderFailure({ status: "could_not_write", message: "m" }), true);
  assert.equal(isFounderFailure({ kind: "founder_brief", readiness: [] }), false);
});
