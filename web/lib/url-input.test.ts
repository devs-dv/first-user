import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanUrlInput, valueAfterPaste } from "./url-input.ts";

test("a leading http:// or https:// is dropped, whatever its case", () => {
  assert.equal(cleanUrlInput("https://example.com"), "example.com");
  assert.equal(cleanUrlInput("http://example.com/pricing?a=1"), "example.com/pricing?a=1");
  assert.equal(cleanUrlInput("HTTPS://Example.com"), "Example.com");
  assert.equal(cleanUrlInput("HtTp://example.com"), "example.com");
});

test("spaces around the address are dropped", () => {
  assert.equal(cleanUrlInput("   https://example.com  "), "example.com");
  assert.equal(cleanUrlInput("\texample.com\n"), "example.com");
  assert.equal(cleanUrlInput("   "), "");
});

test("www. goes only when it came with a protocol", () => {
  assert.equal(cleanUrlInput("https://www.example.com"), "example.com");
  assert.equal(cleanUrlInput("http://WWW.example.com/a"), "example.com/a");
  assert.equal(cleanUrlInput("www.example.com"), "www.example.com");
  assert.equal(cleanUrlInput("  www.example.com "), "www.example.com");
});

test("nothing else is changed", () => {
  assert.equal(cleanUrlInput("example.com"), "example.com");
  assert.equal(cleanUrlInput("https://wwwexample.com"), "wwwexample.com");
  assert.equal(cleanUrlInput("https://app.www.example.com"), "app.www.example.com");
  assert.equal(cleanUrlInput("example.com/https://other"), "example.com/https://other");
  assert.equal(cleanUrlInput("ftp://example.com"), "ftp://example.com");
  assert.equal(cleanUrlInput("https:/example.com"), "https:/example.com");
  assert.equal(cleanUrlInput("https://example.com/www.x"), "example.com/www.x");
  // Only one protocol is a protocol; a second one is part of what was typed.
  assert.equal(cleanUrlInput("https://https://example.com"), "https://example.com");
});

test("a paste replaces the selection, then the whole value is cleaned", () => {
  assert.equal(valueAfterPaste("", "https://www.example.com/app", 0, 0), "example.com/app");
  assert.equal(valueAfterPaste("old.com", " https://new.com ", 0, 7), "new.com");
  assert.equal(valueAfterPaste("example.com", "/pricing", 11, 11), "example.com/pricing");
  assert.equal(valueAfterPaste("abc", "https://x.com", null, null), "abchttps://x.com");
  assert.equal(valueAfterPaste("https://", "example.com", 8, 8), "example.com");
});
