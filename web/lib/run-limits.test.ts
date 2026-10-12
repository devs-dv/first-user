import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_RUNS_PER_HOUR, rateLimitMessage, rateLimited, runsPerHourFrom } from "./run-limits.ts";

test("RUNS_PER_HOUR sets the hourly limit; missing or odd values keep the default of 5", () => {
  assert.equal(DEFAULT_RUNS_PER_HOUR, 5);
  assert.equal(runsPerHourFrom(undefined), 5);
  assert.equal(runsPerHourFrom(""), 5);
  assert.equal(runsPerHourFrom("12"), 12);
  assert.equal(runsPerHourFrom(" 3 "), 3);
  for (const odd of ["0", "-2", "2.5", "ten", "1e3", "100000"]) assert.equal(runsPerHourFrom(odd), 5, odd);
});

test("the limit message says how many runs are left and when the next one frees up", () => {
  assert.equal(
    rateLimitMessage(5, 1500),
    "You've used 5 of 5 runs this hour, so you have 0 left. You can start another in about 25 minutes.",
  );
  assert.equal(
    rateLimitMessage(1, 30),
    "You've used 1 of 1 run this hour, so you have 0 left. You can start another in about 1 minute.",
  );
});

test("the 429 answer carries the limit, the runs left and Retry-After", async () => {
  const response = rateLimited(8, 600, { "Cache-Control": "no-store" });
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("Retry-After"), "600");
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  const body = await response.json();
  assert.equal(body.error, "rate_limited");
  assert.equal(body.limit, 8);
  assert.equal(body.remaining, 0);
  assert.match(body.message, /8 of 8 runs this hour, so you have 0 left/);
});
