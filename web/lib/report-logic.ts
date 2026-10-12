// Small rules of the report page, kept apart from the components so they can be tested with Node alone
// (npm test). Types only are imported, so this file has no runtime dependencies.

import type { Finding, Friction, Run, Step } from "./types.ts";

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
