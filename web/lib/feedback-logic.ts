// Rules of finding feedback, kept apart from the route so they can be tested with Node alone (npm test).
// Types only are imported: no runtime dependencies.

import type { Finding } from "./types.ts";

export const FEEDBACK_VERDICTS = ["useful", "not_a_problem", "fixed"] as const;
export type FeedbackVerdict = (typeof FEEDBACK_VERDICTS)[number];

export const MAX_FINDING_ID_LENGTH = 64;
const FINDING_ID = /^[A-Za-z0-9_.:-]{1,64}$/;

export function isVerdict(value: unknown): value is FeedbackVerdict {
  return typeof value === "string" && (FEEDBACK_VERDICTS as readonly string[]).includes(value);
}

export function isFindingId(value: unknown): value is string {
  return typeof value === "string" && FINDING_ID.test(value);
}

// The ids a run's findings have. A finding that carries its own `id` string keeps it; otherwise it is
// "f" and its position in the run's findings list ("f0" is the first). The report page uses the same rule.
export function findingIds(findings: (Finding & { id?: unknown })[] | null | undefined): string[] {
  return (findings ?? []).map((finding, index) =>
    isFindingId(finding?.id) ? (finding.id as string) : `f${index}`,
  );
}

export type FeedbackInput = { findingId: string; verdict: FeedbackVerdict };

// The request body of POST /api/runs/[id]/feedback, or the reason it is not acceptable.
export function parseFeedback(body: unknown):
  | { ok: true; value: FeedbackInput }
  | { ok: false; error: "invalid_request" | "invalid_finding" | "invalid_verdict"; message: string } {
  if (!body || typeof body !== "object") {
    return { ok: false, error: "invalid_request", message: "The request could not be read." };
  }
  const { findingId, verdict } = body as Record<string, unknown>;
  if (!isFindingId(findingId)) {
    return { ok: false, error: "invalid_finding", message: "Say which finding this is about." };
  }
  if (!isVerdict(verdict)) {
    return { ok: false, error: "invalid_verdict", message: "The answer must be useful, not_a_problem or fixed." };
  }
  return { ok: true, value: { findingId, verdict } };
}
