// The words of the site's <title>, description and share cards (Open Graph, X). Kept apart from the pages so they
// can be tested with Node alone (npm test). The share image itself is public/og.png.

import { siteName, verdictKindOf } from "./report-view.ts";
import type { Run } from "./types.ts";
import { derivedHeadline, VERDICT_LOOK } from "./verdict-look.ts";

export const SITE_TITLE = "First User: Your first user, before the real ones.";
export const SITE_DESCRIPTION =
  "An AI that tries your app like a first-time customer, shows where it gets stuck with evidence, gives you a fix prompt, and checks your fix.";
// The root layout adds this to every page title but the home page's.
export const TITLE_TEMPLATE = "%s · First User";

export type PageText = { title: string; description: string };

export type ReportMetaRun = Pick<Run, "url" | "status" | "outcome" | "verdict" | "entry">;

// A report: "{site}: {verdict headline}", with the verdict in the description. A run still under way, or one
// that cannot be read, gets a plain title.
export function reportMeta(run: ReportMetaRun | null): PageText {
  if (!run) return { title: "Visit report", description: SITE_DESCRIPTION };
  const site = siteName(run.url);
  if (run.status === "queued" || run.status === "running") {
    return {
      title: `${site}: visit in progress`,
      description: `First User is trying ${site} like a first-time customer, in a real browser. The report appears here when it finishes.`,
    };
  }
  const kind = verdictKindOf(run, false);
  const headline = run.verdict?.headline?.trim() || derivedHeadline(kind, "");
  return {
    title: `${site}: ${headline}`,
    description: `Verdict: ${VERDICT_LOOK[kind].label}. ${withStop(headline)} First User tried ${site} like a first-time customer and shows the evidence for every step.`,
  };
}

export function briefMeta(url: string | null): PageText {
  if (!url) return { title: "Product brief", description: SITE_DESCRIPTION };
  const site = siteName(url);
  return {
    title: `${site} brief`,
    description: `First User read the public pages of ${site} and suggested what a first-time visitor should try.`,
  };
}

function withStop(text: string): string {
  return /[.!?…]$/.test(text) ? text : `${text}.`;
}
