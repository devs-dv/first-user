// Small rules of the report page, kept apart from the components so they can be tested with Node alone
// (npm test). Types only are imported, so this file has no runtime dependencies.

import { withoutNotice } from "./hidden-text.ts";
import type { Basis, FirstImpression, Finding, Friction, Run, Step, Verdict } from "./types.ts";

function pathOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).pathname || "/";
  } catch {
    return null;
  }
}

// Did the visitor get past the login before it was stopped? Only then is a later block (at checkout, say)
// not a login block.
//
// The worker records this itself for runs from now on: a test login that worked, an account the visitor
// created, or a login written on the page that was accepted (entry.page_login_worked). Runs saved before
// that carry only entry.page_login, so for those, a page login followed by steps on another page than the
// one it was typed on counts as having got in.
export function gotPastLogin(run: Run, steps: Step[]): boolean {
  const entry = run.entry;
  if (!entry) return false;
  if (entry.test_login === "used" || entry.self_signup === "used" || entry.page_login_worked) return true;
  if (entry.page_login === "shown_on_page" && entry.page_login_worked === undefined) {
    const first = pathOf(steps.find((step) => step.url)?.url);
    return first !== null && steps.some((step) => {
      const path = pathOf(step.url);
      return path !== null && path !== first;
    });
  }
  return false;
}

// The three-ways-in help is for a run that was blocked at a login or sign-up step, and only that.
export function showLoginWallHelp(run: Run, steps: Step[]): boolean {
  if (run.entry?.bot_check) return false; // a bot check is not a login
  return run.outcome === "blocked" && !!run.entry?.blocked_at_login && !gotPastLogin(run, steps);
}

// The noted problems that did not become findings. A finding says which noted problems it covers
// (covers_steps, by the step the visitor noted them at); a problem noted at the finding's own step
// also counts as covered, which is how findings from before covers_steps was written are matched.
export function frictionsNotInFindings(frictions: Friction[], findings: Finding[] | null): Friction[] {
  if (!findings || findings.length === 0) return frictions;
  const covered = new Set<number>();
  for (const finding of findings) {
    for (const step of finding.covers_steps ?? []) covered.add(step);
    covered.add(finding.evidence.step);
    for (const seen of finding.also_seen_at ?? []) covered.add(seen.step);
  }
  return frictions.filter((friction) => friction.step_idx === null || !covered.has(friction.step_idx));
}

// ---------------------------------------------------------------------------------------------------
// The three answers at the top of the report (Report v2).

export type Understanding = {
  level: "clear" | "partly" | "unclear";
  label: string;
  reasons: string[];
};

const UNDERSTANDING_LABEL = { clear: "Clear", partly: "Partly clear", unclear: "Unclear" } as const;

// Will a newcomer understand the product? From the first-impression review of the landing page:
// "unclear" when what it does is not clear, or two of the three are not; "clear" when all three are;
// "partly clear" otherwise. The reasons are the review's own words for what was not clear, and its
// hesitations. null when there was no review.
export function understanding(review: FirstImpression | null): Understanding | null {
  if (!review) return null;
  const parts = [
    { name: "What it does", level: review.what_it_does?.clear, summary: review.what_it_does?.summary },
    { name: "Who it is for", level: review.who_its_for?.clear, summary: review.who_its_for?.summary },
    { name: "The main action", level: review.main_action?.obvious, summary: review.main_action?.summary },
  ];
  if (parts.every((part) => !part.level)) return null;
  const noCount = parts.filter((part) => part.level === "no").length;
  const allYes = parts.every((part) => part.level === "yes");
  const level = review.what_it_does?.clear === "no" || noCount >= 2 ? "unclear" : allYes ? "clear" : "partly";
  const reasons = parts
    .filter((part) => part.level !== "yes" && part.summary)
    .map((part) => `${part.name}: ${part.summary}`);
  // The hidden-text notice is shown as its own line, not as a reason (lib/hidden-text.ts).
  reasons.push(...withoutNotice(review.hesitations).slice(0, 2));
  return { level, label: UNDERSTANDING_LABEL[level], reasons };
}

export type FixFirst =
  | { state: "finding"; finding: Finding }
  | { state: "none" }
  | { state: "not_about_site" }
  | { state: "unavailable" };

// What to fix first: the top-ranked finding. For a visit that says nothing about the site (a bot check, or
// a failure on our side) there is nothing to fix from it, and the answer says so rather than inventing one.
export function fixFirst(findings: Finding[] | null, verdict: Verdict | null): FixFirst {
  if (verdict && (verdict.kind === "bot_check" || verdict.kind === "our_failure")) return { state: "not_about_site" };
  if (findings === null) return { state: "unavailable" };
  return findings.length > 0 ? { state: "finding", finding: findings[0] } : { state: "none" };
}

// What a verdict rests on, as the label the page shows.
export const BASIS_LABEL: Record<Basis, string> = {
  observed: "Observed in the run",
  verified: "Verified by an independent check",
  recommendation: "Our recommendation",
};

export const BASIS_NOTE: Record<Basis, string> = {
  observed: "From the record of what the visitor did and what the page did.",
  verified: "Confirmed by a separate check of the final page and the record.",
  recommendation: "Our suggestion. It is not a measured result and promises no outcome.",
};

// Words that would make a recommendation read as a promise. Used to refuse to show them: the worker removes
// such sentences, and this is the second line for reports saved before that.
const PROMISE = /(\bconversions?\b|\b(boost|lift|uplift)s?\b|\d+(\.\d+)?\s?(%|percent)|\bwill (increase|improve|boost|double|result|guarantee)\b|\bguarantee[sd]?\b|\bROI\b)/i;

export function withoutPromises(text: string): string {
  return text
    .split(/(?<=[.!?])\s+/)
    .filter((sentence) => sentence && !PROMISE.test(sentence))
    .join(" ");
}

export function shortUrl(url: string | null | undefined): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${parsed.host}${path}`;
  } catch {
    return url;
  }
}
