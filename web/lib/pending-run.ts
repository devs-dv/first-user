// What a run was started with (address and goal), remembered in this browser tab for the moment between
// starting it and its first response, so the waiting page can show them at once. Presentation only: nothing is
// sent anywhere, and storage that is missing or throws just means the page waits for the server.

export type PendingRun = { url: string; goal: string };

function key(id: string): string {
  return `fu-run:${id}`;
}

export function rememberPendingRun(id: string, run: PendingRun): void {
  try {
    sessionStorage.setItem(key(id), JSON.stringify({ url: run.url, goal: run.goal }));
  } catch {
    // The waiting page shows the address once the server answers.
  }
}

// The id at the end of the page's address (/run/<id>, /brief/<id>), for a loading state that is prerendered and
// so cannot ask the router for it. Browser only.
export function idFromPath(): string {
  return window.location.pathname.split("/").filter(Boolean).pop() ?? "";
}

// The raw stored string (a stable snapshot for useSyncExternalStore), or null.
export function pendingRunSnapshot(id: string): string | null {
  try {
    return sessionStorage.getItem(key(id));
  } catch {
    return null;
  }
}

export function parsePendingRun(raw: string | null): PendingRun | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingRun>;
    return typeof value.url === "string" && typeof value.goal === "string" ? { url: value.url, goal: value.goal } : null;
  } catch {
    return null;
  }
}
