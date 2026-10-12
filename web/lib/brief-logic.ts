// Small rules of the brief page and of starting a test from it, kept apart from the components so they
// can be tested with Node alone (npm test). Types only are imported: no runtime dependencies.

import type { Brief, BriefClaim, BriefFailure, ClaimStatus, HiddenTextNote } from "./brief-types.ts";

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

// The address the test form opens at for one journey, with the goal and success as the visitor edited them.
export function testJourneyHref(briefId: string, siteUrl: string, goal: string, success: string): string {
  const params = new URLSearchParams();
  params.set("mode", "test");
  params.set("url", siteUrl);
  params.set("goal", goal.trim().slice(0, MAX_GOAL_LENGTH));
  if (success.trim()) params.set("success", success.trim().slice(0, MAX_SUCCESS_LENGTH));
  params.set("brief", briefId);
  return `/?${params.toString()}`;
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
