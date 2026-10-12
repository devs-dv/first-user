import assert from "node:assert/strict";
import { test } from "node:test";

import { RELOAD_GAP_MS, isChunkLoadError, isOwnAssetUrl, mayReload } from "./version-skew.ts";

test("failed code loads are recognised in every browser's wording", () => {
  const chunk = new Error("Loading chunk 4821 failed.\n(error: https://x.example/_next/static/chunks/4821.js)");
  chunk.name = "ChunkLoadError";
  assert.equal(isChunkLoadError(chunk), true);
  assert.equal(isChunkLoadError(new Error("Loading CSS chunk app-page failed")), true);
  assert.equal(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: https://x/_next/static/a.js")), true);
  assert.equal(isChunkLoadError(new TypeError("error loading dynamically imported module")), true);
  assert.equal(isChunkLoadError(new TypeError("Importing a module script failed.")), true);
  assert.equal(isChunkLoadError("ChunkLoadError: Loading chunk 12 failed."), true);
});

test("other errors are left alone", () => {
  assert.equal(isChunkLoadError(new Error("Cannot read properties of undefined")), false);
  assert.equal(isChunkLoadError(new TypeError("Failed to fetch")), false);
  assert.equal(isChunkLoadError(null), false);
  assert.equal(isChunkLoadError({ message: 42 }), false);
});

test("only the app's own build files count as failed assets", () => {
  assert.equal(isOwnAssetUrl("https://first-user.example/_next/static/chunks/app/page-abc.js"), true);
  assert.equal(isOwnAssetUrl("/_next/static/css/1234.css"), true);
  assert.equal(isOwnAssetUrl("https://cdn.example/analytics.js"), false);
  assert.equal(isOwnAssetUrl(""), false);
  assert.equal(isOwnAssetUrl(null), false);
});

test("at most one automatic reload a minute", () => {
  const now = 1_000_000_000;
  assert.equal(mayReload(null, now), true);
  assert.equal(mayReload(String(now - RELOAD_GAP_MS), now), true);
  assert.equal(mayReload(String(now - 5_000), now), false);
  assert.equal(mayReload("not a time", now), true);
  assert.equal(mayReload(String(now + 120_000), now), true, "a stored time in the future (a changed clock) does not block for ever");
});
