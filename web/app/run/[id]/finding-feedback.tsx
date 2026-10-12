"use client";

// The founder's answer to a finding: Useful, Not a real problem, or I fixed this. Saved by
// POST /api/runs/[id]/feedback; the browser remembers the visitor's vote so a reload keeps it. Kept in its
// own file so the report page changes little and the feature can be hidden by flag (lib/report-flags.ts).

import { useState } from "react";

import {
  FEEDBACK_VERDICTS,
  VERDICT_LABELS,
  readStoredVotes,
  storeVote,
  type FeedbackVerdict,
} from "@/lib/feedback-logic";

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

type Status = "idle" | "saving" | "saved" | "failed";

export function FindingFeedback({
  runId,
  findingId,
  checkAgain,
}: {
  runId: string;
  findingId: string;
  checkAgain: boolean;
}) {
  // The report renders only after the run is fetched in the browser, so reading storage here cannot
  // differ from a server render.
  const [vote, setVote] = useState<FeedbackVerdict | null>(
    () => readStoredVotes(browserStorage(), runId)[findingId] ?? null,
  );
  const [status, setStatus] = useState<Status>("idle");

  async function send(verdict: FeedbackVerdict) {
    setStatus("saving");
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ findingId, verdict }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setVote(verdict);
      storeVote(browserStorage(), runId, findingId, verdict);
      setStatus("saved");
    } catch {
      // The earlier vote, if any, stays selected: it is still the one the server has.
      setStatus("failed");
    }
  }

  return (
    <div className="flex flex-col items-end gap-1.5 text-[13px]">
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        <span className="mr-1 text-ink3">Was this right?</span>
        <div role="group" aria-label="Your answer to this finding" className="flex flex-wrap gap-1.5">
          {FEEDBACK_VERDICTS.map((verdict) => {
            const chosen = vote === verdict;
            return (
              <button
                key={verdict}
                type="button"
                aria-pressed={chosen}
                disabled={status === "saving"}
                onClick={() => send(verdict)}
                className="h-9 cursor-pointer whitespace-nowrap rounded-pill px-3 text-[13px] font-medium text-ink transition-colors disabled:cursor-default disabled:opacity-60"
                style={{
                  border: `1px solid ${chosen ? "var(--ink)" : "var(--line)"}`,
                  background: chosen ? "var(--acc-soft)" : "transparent",
                }}
              >
                {chosen && <span aria-hidden>✓ </span>}
                {VERDICT_LABELS[verdict]}
              </button>
            );
          })}
        </div>
      </div>
      <span aria-live="polite" className="text-ink3">
        {status === "saved" && "Thanks."}
        {status === "failed" && <span className="text-bad-ink">Couldn&apos;t save, try again.</span>}
      </span>
      {vote === "fixed" && checkAgain && (
        <a href="#check-again" className="fu-link font-medium">
          Check again to confirm it
        </a>
      )}
    </div>
  );
}
