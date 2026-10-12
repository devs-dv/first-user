"use client";

// "Your recent runs": the last ten briefs and tests started from this browser. The list lives in
// localStorage (lib/recent-runs.ts) and holds only ids, kinds, site names and times; each run's status is
// read from the server. Hidden when the list is empty.

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { parseRecent, timeAgo } from "@/lib/journey-progress";
import { clearRecent, recentSnapshot, subscribeRecent } from "@/lib/recent-runs";
import type { RunStatus, VerdictKind } from "@/lib/types";

import { RunStatusChip } from "../run-status-chip";

type Status = { status: RunStatus; verdict_kind: VerdictKind | null };

export function RecentRuns() {
  const raw = useSyncExternalStore(subscribeRecent, recentSnapshot, () => null);
  const runs = useMemo(() => parseRecent(raw), [raw]);
  const ids = runs.map((run) => run.id).join(",");
  const [statuses, setStatuses] = useState<Record<string, Status>>({});
  // Read once when the list shows, for the "time ago" labels. Null on the server.
  const now = useSyncExternalStore(noSubscription, mountedNow, () => null);

  useEffect(() => {
    if (!ids) return;
    let cancelled = false;
    fetch(`/api/runs/status?ids=${encodeURIComponent(ids)}`, { cache: "no-store" })
      .then((response) => (response.ok ? (response.json() as Promise<{ runs: ({ id: string } & Status)[] }>) : null))
      .then((body) => {
        if (cancelled || !body) return;
        setStatuses(Object.fromEntries(body.runs.map((run) => [run.id, { status: run.status, verdict_kind: run.verdict_kind }])));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [ids]);

  if (runs.length === 0) return null;
  return (
    <section aria-labelledby="fu-recent-title" className="bg-s1" style={{ padding: "0 var(--gutter) var(--section-y)" }}>
      <div className="mx-auto flex max-w-[760px] flex-col gap-3 rounded-cardsm border-[1.5px] border-ink bg-bg p-[clamp(16px,2.4cqi,22px)]">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="fu-recent-title" className="m-0 text-[17px] font-semibold">
            Your recent runs
          </h2>
          <button type="button" onClick={clearRecent} className="fu-link cursor-pointer border-none bg-transparent p-0 text-[14px] text-ink3">
            Clear
          </button>
        </div>
        <ul className="m-0 flex list-none flex-col p-0">
          {runs.map((run, index) => {
            const status = statuses[run.id];
            const href = run.kind === "brief" ? `/brief/${run.id}` : `/run/${run.id}`;
            return (
              <li key={run.id} style={{ borderTop: index ? "1px solid var(--line)" : "none" }}>
                <Link href={href} className="flex items-center gap-3 py-2.5 text-ink no-underline hover:bg-s1 focus-visible:bg-s1">
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate text-[15px] font-semibold">{run.site}</span>
                    <span className="font-code text-[12px] text-ink3">
                      {run.kind === "brief" ? "Brief" : "Test"}
                      {now !== null && (
                        <>
                          {" · "}
                          <time dateTime={run.at}>{timeAgo(run.at, now)}</time>
                        </>
                      )}
                    </span>
                  </span>
                  {status ? (
                    <RunStatusChip status={status.status} verdictKind={status.verdict_kind} brief={run.kind === "brief"} />
                  ) : (
                    <span className="fu-chip fu-chip-word bg-s2 text-ink3">…</span>
                  )}
                  <span aria-hidden className="text-ink3">→</span>
                </Link>
              </li>
            );
          })}
        </ul>
        <p className="m-0 text-[12px] leading-normal text-ink3">
          Kept in this browser only: the site name, the kind of run and when it started. Never goals or logins.
        </p>
      </div>
    </section>
  );
}

const noSubscription = () => () => {};
let mountedAt: number | null = null;
function mountedNow(): number {
  mountedAt ??= Date.now();
  return mountedAt;
}
