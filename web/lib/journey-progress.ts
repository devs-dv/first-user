// Rules that tie a brief to the tests started from it, and this browser's list of recent runs, kept apart
// from the components so they can be tested with Node alone (npm test). Types only are imported.

import type { SuggestedJourney } from "./brief-types.ts";
import type { Outcome, RunStatus, VerdictKind } from "./types.ts";

// ---------------------------------------------------------------------------------------------------
// A test run started from a brief, as GET /api/briefs/[id]/runs returns it: nothing else of the run.

export type BriefTestRun = { id: string; goal: string; status: RunStatus; verdict_kind: VerdictKind | null };

// The verdict kind of a finished run, from the columns the list reads: the verdict when the worker wrote one,
// otherwise the outcome (as verdictKindOf does, without the steps that tell a login wall apart from stuck).
export function listedVerdictKind(row: {
  status: RunStatus;
  verdict_kind: string | null;
  outcome: Outcome | null;
  bot_check: unknown;
}): VerdictKind | null {
  if (row.status === "queued" || row.status === "running") return null;
  if (row.verdict_kind && row.verdict_kind in KIND_SET) return row.verdict_kind as VerdictKind;
  if (row.status === "failed") return "our_failure";
  if (row.bot_check) return "bot_check";
  switch (row.outcome) {
    case "achieved":
      return "got_through";
    case "achieved_unconfirmed":
    case "unverified":
      return "unconfirmed";
    case "error":
    case null:
      return "our_failure";
    default:
      return "stuck";
  }
}

const KIND_SET: Record<VerdictKind, true> = {
  got_through: true,
  unconfirmed: true,
  stuck: true,
  login_wall: true,
  bot_check: true,
  our_failure: true,
};

// Goals match when they read the same, ignoring case, spacing and a trailing full stop.
export function sameGoal(a: string, b: string): boolean {
  const norm = (value: string) => value.trim().replace(/\s+/g, " ").replace(/\.$/, "").toLowerCase();
  return norm(a) !== "" && norm(a) === norm(b);
}

// The newest test of this journey, or null. `runs` come newest first.
export function runForJourney(journey: Pick<SuggestedJourney, "goal">, runs: BriefTestRun[]): BriefTestRun | null {
  return runs.find((run) => sameGoal(run.goal, journey.goal)) ?? null;
}

// The brief's suggested journeys no test from it has used yet, keeping their order.
export function untestedJourneys(journeys: SuggestedJourney[], runs: BriefTestRun[]): SuggestedJourney[] {
  return journeys.filter((journey) => !runForJourney(journey, runs));
}

// ---------------------------------------------------------------------------------------------------
// Recent runs started from this browser (localStorage). Only the run's id, kind, site name and time: never
// the goal, the address's path or anything typed into the login fields.

export type RecentKind = "test" | "brief";
export type RecentRun = { id: string; kind: RecentKind; site: string; at: string };

export const RECENT_KEY = "fu-recent";
export const RECENT_MAX = 10;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// The stored list with anything odd dropped. A missing or broken value is an empty list.
export function parseRecent(raw: string | null): RecentRun[] {
  if (!raw) return [];
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(value)) return [];
  const runs: RecentRun[] = [];
  for (const item of value) {
    const { id, kind, site, at } = (item ?? {}) as Partial<RecentRun>;
    if (typeof id !== "string" || !UUID.test(id)) continue;
    if (kind !== "test" && kind !== "brief") continue;
    if (typeof site !== "string" || typeof at !== "string" || Number.isNaN(Date.parse(at))) continue;
    runs.push({ id, kind, site: site.slice(0, 120), at });
  }
  return runs.slice(0, RECENT_MAX);
}

// The list with `run` first, without an earlier copy of it, cut to the last ten.
export function addRecent(list: RecentRun[], run: RecentRun): RecentRun[] {
  return [run, ...list.filter((item) => item.id !== run.id)].slice(0, RECENT_MAX);
}

// "just now", "5 min ago", "3 h ago", "2 days ago", then the date.
export function timeAgo(at: string, now: number): string {
  const seconds = Math.max(0, (now - Date.parse(at)) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  const days = Math.floor(seconds / 86400);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(at).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// The host of what was typed in the address field ("app.example.com"), never its path, query or any
// user:password in it. The field shows "https://" in front, so the typed text may have no scheme.
export function recentSite(address: string): string {
  const trimmed = address.trim();
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    return new URL(withScheme).host.replace(/^www\./, "").slice(0, 120);
  } catch {
    return (trimmed.split(/[/?#]/)[0].split("@").pop() ?? "").slice(0, 120);
  }
}
