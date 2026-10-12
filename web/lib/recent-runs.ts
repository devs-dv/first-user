// This browser's recent runs (localStorage), with a tiny store so the home page's list updates when one is
// added or cleared. Storage that is missing or throws just means an empty list.

import { addRecent, parseRecent, RECENT_KEY, type RecentRun } from "./journey-progress.ts";

const listeners = new Set<() => void>();

export function subscribeRecent(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

// The raw stored string (a stable snapshot for useSyncExternalStore), or null.
export function recentSnapshot(): string | null {
  try {
    return localStorage.getItem(RECENT_KEY);
  } catch {
    return null;
  }
}

export function rememberRecent(run: RecentRun): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(addRecent(parseRecent(recentSnapshot()), run)));
  } catch {
    // The list just won't show this run.
  }
  listeners.forEach((listener) => listener());
}

export function clearRecent(): void {
  try {
    localStorage.removeItem(RECENT_KEY);
  } catch {
    // Nothing to clear.
  }
  listeners.forEach((listener) => listener());
}
