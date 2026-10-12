// The test form's draft (goal, success condition and the chosen way in), kept in this browser tab so a reload
// doesn't lose it. Never the test login, nor the start link (it can carry a guest token). Storage that is
// missing or throws just means no draft.

import type { AccessMode } from "./types.ts";

export type TestDraft = { goal: string; success: string; access: AccessMode };

const KEY = "fu-test-draft";
const ACCESS: AccessMode[] = ["public", "link", "account", "signup"];

export function parseDraft(raw: string | null): TestDraft | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<TestDraft>;
    return {
      goal: typeof value.goal === "string" ? value.goal.slice(0, 500) : "",
      success: typeof value.success === "string" ? value.success.slice(0, 300) : "",
      access: ACCESS.includes(value.access as AccessMode) ? (value.access as AccessMode) : "public",
    };
  } catch {
    return null;
  }
}

export function readDraft(): TestDraft | null {
  try {
    return parseDraft(sessionStorage.getItem(KEY));
  } catch {
    return null;
  }
}

export function saveDraft(draft: TestDraft): void {
  try {
    if (!draft.goal && !draft.success && draft.access === "public") sessionStorage.removeItem(KEY);
    else sessionStorage.setItem(KEY, JSON.stringify({ goal: draft.goal, success: draft.success, access: draft.access }));
  } catch {
    // Without storage the draft lasts until the page is reloaded.
  }
}

export function clearDraft(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Nothing to clear.
  }
}
