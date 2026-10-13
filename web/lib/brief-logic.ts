// Small rules of the brief page and of starting a test from it, kept apart from the components so they
// can be tested with Node alone (npm test). Types only are imported: no runtime dependencies.

import type { Brief, BriefClaim, BriefFailure, BriefProgress, BriefRun, ClaimStatus, HiddenTextNote } from "./brief-types.ts";

export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const MAX_GOAL_LENGTH = 500;
export const MAX_SUCCESS_LENGTH = 300;

// The record of hidden text a brief carries, or null. Only its presence matters: the page shows its own fixed
// notice (HIDDEN_TEXT_NOTICE), never wording from the data, and the record holds no page text.
export function hiddenTextNote(value: unknown): HiddenTextNote | null {
  const note = (value as { hidden_text?: HiddenTextNote | null } | null)?.hidden_text;
  if (!note || typeof note !== "object" || !Array.isArray(note.found) || note.found.length === 0) return null;
  return note;
}

export function isBrief(value: unknown): value is Brief {
  const brief = value as Brief | null;
  return !!brief && typeof brief === "object" && typeof brief.one_liner === "string" && Array.isArray(brief.claims);
}

export function isFailure(value: unknown): value is BriefFailure {
  const failure = value as BriefFailure | null;
  return !!failure && typeof failure === "object" && failure.status === "could_not_read";
}

// The waiting page's phases, in order. "done" is the brief itself; a failed run shows its own message instead.
export type BriefPhase = "queued" | "reading" | "writing" | "done";
export const BRIEF_PHASES: BriefPhase[] = ["queued", "reading", "writing", "done"];
// With nothing new for this long, the waiting page says the read is still going.
export const BRIEF_STALL_MS = 90_000;

function progressOf(value: unknown): BriefProgress | null {
  const progress = value as BriefProgress | null;
  if (!progress || typeof progress !== "object" || (progress.status !== "reading" && progress.status !== "writing")) return null;
  return progress;
}

// Where a brief run is, and how many pages it has read when the worker says so (null when it does not, as an
// older worker or a run that has not read a page yet).
export function briefProgress(run: Pick<BriefRun, "status" | "brief">): { phase: BriefPhase; pagesRead: number | null } {
  if (run.status === "done") return { phase: "done", pagesRead: null };
  if (run.status === "queued") return { phase: "queued", pagesRead: null };
  const progress = progressOf(run.brief);
  const count = progress?.pages_read;
  const pagesRead = typeof count === "number" && Number.isInteger(count) && count > 0 ? count : null;
  return { phase: progress?.status === "writing" ? "writing" : "reading", pagesRead };
}

// What the brief says when something was not on the pages it read. Understand reads only a few pages, so it can
// say it did not find a thing there, never that the site does not have it. The count is left out when unknown.
export function notFoundLabel(pagesRead: number | null | undefined): string {
  if (typeof pagesRead !== "number" || !Number.isInteger(pagesRead) || pagesRead < 1) return "Not found on the pages read";
  return `Not found in the ${pagesRead} page${pagesRead === 1 ? "" : "s"} read`;
}

// Only http(s) addresses become links: a page's own text never gets to write a javascript: link.
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

const STATUS_ORDER: ClaimStatus[] = ["confirmed", "inferred", "unknown"];

// Stated on the site first, then inferred, then unknown. Stable inside each group.
export function sortClaims(claims: BriefClaim[]): BriefClaim[] {
  return claims
    .map((claim, index) => ({ claim, index }))
    .sort((a, b) => STATUS_ORDER.indexOf(a.claim.status) - STATUS_ORDER.indexOf(b.claim.status) || a.index - b.index)
    .map(({ claim }) => claim);
}

// The address the test form opens at for one journey, with the goal and success as the visitor edited them. It
// ends at the form's anchor (lib/site.ts FORM_ANCHOR), so the visitor lands on the form, not the top of the page.
export function testJourneyHref(briefId: string, siteUrl: string, goal: string, success: string): string {
  const params = new URLSearchParams();
  params.set("mode", "test");
  params.set("url", siteUrl);
  params.set("goal", goal.trim().slice(0, MAX_GOAL_LENGTH));
  if (success.trim()) params.set("success", success.trim().slice(0, MAX_SUCCESS_LENGTH));
  params.set("brief", briefId);
  return `/?${params.toString()}#fu-form`;
}

export type HomeParams = { mode: "test" | "understand"; url: string; goal: string; success: string; brief: string };

// What the home page takes from its address, with anything odd dropped.
export function parseHomeParams(raw: Record<string, string | string[] | undefined>): HomeParams {
  const one = (key: string) => {
    const value = raw[key];
    return typeof value === "string" ? value : Array.isArray(value) ? (value[0] ?? "") : "";
  };
  const brief = one("brief");
  return {
    mode: one("mode") === "understand" ? "understand" : "test",
    url: one("url").slice(0, 2048),
    goal: one("goal").slice(0, MAX_GOAL_LENGTH),
    success: one("success").slice(0, MAX_SUCCESS_LENGTH),
    brief: UUID.test(brief) ? brief : "",
  };
}

// The default post text of the brief page's share panel, for the product brief and for the founder brief.
export function briefShareText(site: string, link: string, which: "product" | "founder"): string {
  return which === "founder"
    ? `First User wrote a founder brief for ${site} from its public pages: ${link} #neatHack via @devsdv_`
    : `First User read ${site} and suggested what a first-time visitor should try. Here's the brief: ${link} #neatHack via @devsdv_`;
}
