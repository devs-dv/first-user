import assert from "node:assert/strict";
import { test } from "node:test";

import { parseHomeParams, testJourneyHref } from "./brief-logic.ts";
import { formStart, hasPrefill } from "./test-draft.ts";

const BRIEF_ID = "0b2f6a5e-5c53-4d6e-9d0a-7c1d0f6a1e11";
const NONE = { url: "", goal: "", success: "", brief: "" };

test("a journey picked on a brief for site Y wins over the draft left by a test of site X, field by field", () => {
  // A test of site X with goal A and success A left this draft behind.
  const draft = { goal: "Goal A on site X", success: "Success A", access: "account" as const };
  // Later: a brief for site Y, "Test this journey" with goal B and no success condition.
  const href = testJourneyHref(BRIEF_ID, "https://site-y.example/", "Goal B on site Y", "");
  const prefill = parseHomeParams(Object.fromEntries(new URL(href, "https://first-user.example").searchParams));
  const start = formStart(prefill, draft);
  assert.equal(prefill.url, "https://site-y.example/");
  assert.equal(start.goal, "Goal B on site Y");
  assert.equal(start.success, "", "an empty success from the brief is not filled in from the draft");
  assert.equal(start.access, "public", "the way in is the default, not the draft's");
  assert.equal(start.dropDraft, true);
});

test("any one prefilled field is a prefill: the draft is dropped and none of it shows", () => {
  const draft = { goal: "Old goal", success: "Old success", access: "link" as const };
  for (const prefill of [
    { ...NONE, url: "https://y.example/" },
    { ...NONE, goal: "New goal" },
    { ...NONE, success: "New success" },
    { ...NONE, brief: BRIEF_ID },
  ]) {
    assert.equal(hasPrefill(prefill), true);
    const start = formStart(prefill, draft);
    assert.equal(start.dropDraft, true);
    assert.notEqual(start.goal, "Old goal");
    assert.notEqual(start.success, "Old success");
    assert.equal(start.access, "public");
  }
});

test("with nothing in the address the draft comes back, and without a draft the form is empty", () => {
  const draft = { goal: "Kept goal", success: "Kept success", access: "signup" as const };
  assert.deepEqual(formStart(NONE, draft), { goal: "Kept goal", success: "Kept success", access: "signup", dropDraft: false });
  assert.deepEqual(formStart(NONE, null), { goal: "", success: "", access: "public", dropDraft: false });
});
