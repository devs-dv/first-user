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

// ------------------------------------------------------------------------------ the report page's buttons

export const VERDICT_LABELS: Record<FeedbackVerdict, string> = {
  useful: "Useful",
  not_a_problem: "Not a real problem",
  fixed: "I fixed this",
};

// The buttons show on a finished report that has findings. A bot check or a failure on our side says
// nothing about the site, so its report has no findings to vote on.
export function feedbackShown(run: {
  status: string;
  findings: unknown[] | null;
  verdict?: { kind: string } | null;
  entry?: { bot_check?: unknown } | null;
}): boolean {
  if (run.status !== "done") return false;
  if (run.verdict?.kind === "bot_check" || run.verdict?.kind === "our_failure") return false;
  if (run.entry?.bot_check) return false;
  return (run.findings?.length ?? 0) > 0;
}

// The visitor's own votes, remembered in the browser so a reload keeps the selection. Only a vote the
// server accepted is written here; the server's table stays the record. Storage can be missing or throw
// (private windows, blocked site data), so every access is guarded and a failure means "nothing remembered".
type VoteStorage = Pick<Storage, "getItem" | "setItem">;

export function feedbackStorageKey(runId: string): string {
  return `feedback:${runId}`;
}

export function readStoredVotes(storage: VoteStorage | null | undefined, runId: string): Record<string, FeedbackVerdict> {
  const votes: Record<string, FeedbackVerdict> = {};
  try {
    const raw = storage?.getItem(feedbackStorageKey(runId));
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return votes;
    for (const [findingId, verdict] of Object.entries(parsed)) {
      if (isFindingId(findingId) && isVerdict(verdict)) votes[findingId] = verdict;
    }
  } catch {
    // Nothing remembered.
  }
  return votes;
}

export function storeVote(
  storage: VoteStorage | null | undefined,
  runId: string,
  findingId: string,
  verdict: FeedbackVerdict,
): void {
  try {
    if (!storage) return;
    const votes = { ...readStoredVotes(storage, runId), [findingId]: verdict };
    storage.setItem(feedbackStorageKey(runId), JSON.stringify(votes));
  } catch {
    // The vote is saved on the server; only the reminder in this browser is lost.
  }
}
