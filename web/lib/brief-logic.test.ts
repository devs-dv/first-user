import assert from "node:assert/strict";
import { test } from "node:test";

import {
  hiddenTextNote,
  isBrief,
  isFailure,
  parseHomeParams,
  safeHref,
  sortClaims,
  testJourneyHref,
} from "./brief-logic.ts";
import { HIDDEN_TEXT_NOTICE, type BriefClaim } from "./brief-types.ts";

const BRIEF_ID = "0b2f6a5e-5c53-4d6e-9d0a-7c1d0f6a1e11";

test("a journey opens the test form with the url, the goal, the success condition and the brief", () => {
  const href = testJourneyHref(BRIEF_ID, "https://acme.example/", "Start a free trial", "A welcome page appears");
  const params = new URL(href, "https://first-user.example").searchParams;
  assert.equal(href.startsWith("/?"), true);
  assert.equal(params.get("mode"), "test");
  assert.equal(params.get("url"), "https://acme.example/");
  assert.equal(params.get("goal"), "Start a free trial");
  assert.equal(params.get("success"), "A welcome page appears");
  assert.equal(params.get("brief"), BRIEF_ID);
});

test("an edited journey is what is sent, trimmed and bounded, and no success is left out of the address", () => {
  const params = new URL(testJourneyHref(BRIEF_ID, "https://a.example/", `  ${"g".repeat(900)}  `, "   "), "https://x.example")
    .searchParams;
  assert.equal(params.get("goal")?.length, 500);
  assert.equal(params.has("success"), false);
});

test("the home page takes only what it understands from its address", () => {
  const parsed = parseHomeParams({ mode: "test", url: "https://a.example/", goal: "g", success: "s", brief: BRIEF_ID });
  assert.deepEqual(parsed, { mode: "test", url: "https://a.example/", goal: "g", success: "s", brief: BRIEF_ID });
  assert.equal(parseHomeParams({ brief: "not-a-uuid" }).brief, "");
  assert.equal(parseHomeParams({ mode: "understand" }).mode, "understand");
  assert.equal(parseHomeParams({ mode: "anything" }).mode, "test");
  assert.equal(parseHomeParams({ goal: ["first", "second"] }).goal, "first");
  assert.equal(parseHomeParams({ url: "x".repeat(5000) }).url.length, 2048);
});

test("only http and https addresses become links", () => {
  assert.equal(safeHref("https://acme.example/pricing"), "https://acme.example/pricing");
  assert.equal(safeHref("javascript:alert(1)"), null);
  assert.equal(safeHref("data:text/html,x"), null);
  assert.equal(safeHref("not a url"), null);
  assert.equal(safeHref(null), null);
});

test("claims are listed stated first, then inferred, then unknown, keeping their order", () => {
  const claim = (name: string, status: BriefClaim["status"]): BriefClaim => ({
    claim: name,
    status,
    source_url: "https://a.example/",
    quote: "",
  });
  const sorted = sortClaims([
    claim("a", "unknown"),
    claim("b", "inferred"),
    claim("c", "confirmed"),
    claim("d", "inferred"),
    claim("e", "confirmed"),
  ]);
  assert.deepEqual(
    sorted.map((c) => c.claim),
    ["c", "e", "b", "d", "a"],
  );
});

test("a brief and a failure are told apart", () => {
  assert.equal(isBrief({ one_liner: "x", claims: [] }), true);
  assert.equal(isBrief({ status: "could_not_read", message: "m" }), false);
  assert.equal(isBrief(null), false);
  assert.equal(isFailure({ status: "could_not_read", message: "m" }), true);
  assert.equal(isFailure({ one_liner: "x", claims: [] }), false);
});

test("a brief with hidden text found carries its record, and one without has none", () => {
  const note = {
    notice: HIDDEN_TEXT_NOTICE,
    found: [{ url: "https://shop.example/review.html", where: "site_reader", method: "html_comment", blocks: 1 }],
  };
  assert.deepEqual(hiddenTextNote({ hidden_text: note }), note);
  assert.equal(hiddenTextNote({ hidden_text: null }), null);
  assert.equal(hiddenTextNote({}), null);
  assert.equal(hiddenTextNote(null), null);
  assert.equal(hiddenTextNote({ hidden_text: { notice: "x", found: [] } }), null);
  assert.equal(hiddenTextNote({ hidden_text: { notice: "x" } }), null);
});

test("the notice wording is the worker's fixed sentence", () => {
  assert.equal(
    HIDDEN_TEXT_NOTICE,
    "This page contains hidden text addressed to automated agents. It is not visible to people and was ignored.",
  );
});
