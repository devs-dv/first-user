"use client";

import { useEffect, useState } from "react";

import type { BriefTestRun } from "./journey-progress.ts";

const POLL_MS = 5000;

// The test runs started from a brief, read again every few seconds while one of them is still going.
// Null until the first answer. A failed read leaves the list as it was: progress is extra information, never a reason to break the page.
export function useBriefRuns(briefId: string | null): BriefTestRun[] | null {
  const [runs, setRuns] = useState<BriefTestRun[] | null>(null);
  useEffect(() => {
    if (!briefId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      let again = true;
      try {
        const response = await fetch(`/api/briefs/${encodeURIComponent(briefId!)}/runs`, { cache: "no-store" });
        if (response.ok) {
          const body = (await response.json()) as { runs?: BriefTestRun[] };
          if (cancelled) return;
          const list = Array.isArray(body.runs) ? body.runs : [];
          setRuns(list);
          again = list.some((run) => run.status === "queued" || run.status === "running");
        }
      } catch {
        // Tried again below.
      }
      if (!cancelled && again) timer = setTimeout(load, POLL_MS);
    }
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [briefId]);
  return runs;
}
