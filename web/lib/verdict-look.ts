// The colour and label of each verdict, shared by the report, the brief's journey cards and the home page's
// recent runs. Types only are imported: no runtime dependencies.

import type { VerdictKind } from "./types.ts";

type Look = { label: string; bg: string; fg: string; chipBg: string; chipFg: string; border: "solid" | "dashed" };

// The six states, each with its own label and colour (design/code, the report's verdict hero).
export const VERDICT_LOOK: Record<VerdictKind, Look> = {
  got_through: { label: "Got through", bg: "var(--acc)", fg: "var(--on-acc)", chipBg: "#0E1320", chipFg: "#C6FF3D", border: "solid" },
  unconfirmed: { label: "Unconfirmed", bg: "var(--amber-soft)", fg: "var(--ink)", chipBg: "var(--warn)", chipFg: "#0E1320", border: "dashed" },
  stuck: { label: "Stuck", bg: "var(--bad)", fg: "var(--on-bad)", chipBg: "#0E1320", chipFg: "#FFFFFF", border: "solid" },
  login_wall: { label: "Login wall", bg: "var(--blue-soft)", fg: "var(--ink)", chipBg: "var(--info)", chipFg: "#0E1320", border: "solid" },
  bot_check: { label: "Bot check", bg: "var(--s2)", fg: "var(--ink)", chipBg: "var(--ink)", chipFg: "var(--bg)", border: "solid" },
  our_failure: { label: "Our failure", bg: "var(--bg)", fg: "var(--ink)", chipBg: "var(--s2)", chipFg: "var(--ink)", border: "dashed" },
};

// The same words the worker writes (worker/verdict.py), for runs saved before it wrote a verdict.
export function derivedHeadline(kind: VerdictKind, page: string): string {
  switch (kind) {
    case "got_through":
      return "A first-time visitor got through";
    case "unconfirmed":
      return "The visitor says it got through, but we could not confirm it";
    case "stuck":
      return page ? `A first-time visitor got stuck on ${page}` : "A first-time visitor got stuck";
    case "login_wall":
      return "A first-time visitor was stopped at a login";
    case "bot_check":
      return "The site blocked the visit with a bot check";
    case "our_failure":
      return "The visit failed on our side, so this says nothing about your site";
  }
}
