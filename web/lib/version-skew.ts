// After a redeploy, a tab opened before it asks for code files the server no longer has, and navigation fails
// until the page is reloaded. These rules spot such a failure and allow one automatic reload a minute, so a
// failure that a reload does not fix can never loop. The form's draft is in sessionStorage, so it survives.

export const RELOAD_KEY = "fu-skew-reload-at";
export const RELOAD_GAP_MS = 60_000;

const CHUNK_MESSAGE =
  /ChunkLoadError|Loading (?:CSS )?chunk [\w./-]+ failed|Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i;

// An error or rejection reason that says a piece of the app's code failed to load.
export function isChunkLoadError(reason: unknown): boolean {
  if (!reason) return false;
  if (typeof reason === "string") return CHUNK_MESSAGE.test(reason);
  const error = reason as { name?: unknown; message?: unknown };
  return (
    (typeof error.name === "string" && error.name === "ChunkLoadError") ||
    (typeof error.message === "string" && CHUNK_MESSAGE.test(error.message))
  );
}

// A <script> or stylesheet of the app's own build that failed to load.
export function isOwnAssetUrl(url: string | null | undefined): boolean {
  return !!url && /\/_next\/static\//.test(url);
}

// One reload a minute at most. A stored time that cannot be read counts as none.
export function mayReload(lastAt: string | null, now: number): boolean {
  if (!lastAt) return true;
  const last = Number(lastAt);
  return !Number.isFinite(last) || now - last >= RELOAD_GAP_MS || now < last;
}
