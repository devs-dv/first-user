// The report's notice for hidden text aimed at AI agents (worker/hidden_text.py). The worker keeps only evidence
// of what it found ({url, step, where, method, blocks}, never the text) in result.hidden_text, and puts a fixed
// notice first in the first impression's hesitations. The page shows its own copy of that notice and fixed labels
// for the hiding methods it knows; nothing stored in the run is shown as text. No React: tested with Node alone.

import { HIDDEN_TEXT_NOTICE } from "./brief-types.ts";
import type { FirstImpression } from "./types.ts";

// The same words as hidden_text.NOTICE in the worker, kept once (lib/brief-types.ts) for the report and the briefs.
export { HIDDEN_TEXT_NOTICE };

export type HiddenTextFind = { url?: unknown; step?: unknown; where?: unknown; method?: unknown; blocks?: unknown };
export type HiddenText = { notice?: unknown; found?: unknown; sentences_removed?: unknown } | null;

const METHOD_LABELS: Record<string, string> = {
  html_comment: "an HTML comment",
  white_on_white: "white text on white",
  off_screen: "text moved off screen",
  clipped: "clipped text",
  transparent: "transparent text",
  tiny_text: "tiny text",
  display_none: "text hidden from view",
  aria_hidden: "text hidden from screen readers",
  attribute: "an attribute",
};

// Fixed labels for the hiding methods in the evidence, once each; methods the page does not know are left out.
export function methodLabels(found: unknown): string[] {
  const labels: string[] = [];
  for (const item of Array.isArray(found) ? (found as HiddenTextFind[]) : []) {
    const label = typeof item?.method === "string" ? METHOD_LABELS[item.method] : undefined;
    if (label && !labels.includes(label)) labels.push(label);
  }
  return labels;
}

function isNotice(text: unknown): boolean {
  return typeof text === "string" && text.trim() === HIDDEN_TEXT_NOTICE;
}

// What the report says about hidden text, or null when none was found. `methods` are fixed labels for the known
// hiding methods (unknown ones are left out); the stored notice and anything else in the evidence is not used.
export function hiddenTextNotice(
  hidden: HiddenText | undefined,
  review: FirstImpression | null,
): { methods: string[] } | null {
  const found = hidden && Array.isArray(hidden.found) ? (hidden.found as HiddenTextFind[]) : [];
  const flagged = (review?.hesitations ?? []).some(isNotice);
  if (found.length === 0 && !flagged) return null;
  return { methods: methodLabels(found) };
}

// The first impression without the notice, which the report shows as its own line instead.
export function withoutNotice(hesitations: string[] | undefined): string[] {
  return (hesitations ?? []).filter((item) => !isNotice(item));
}
