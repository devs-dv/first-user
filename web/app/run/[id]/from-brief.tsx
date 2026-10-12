"use client";

// A test started from a product brief links back to it: a line at the top of the report, and after the
// findings the brief's suggested journeys that no test from it has used yet.

import Link from "next/link";
import { useEffect, useState } from "react";

import { isBrief, testJourneyHref } from "@/lib/brief-logic";
import type { Brief, BriefRun } from "@/lib/brief-types";
import { untestedJourneys } from "@/lib/journey-progress";
import { grid } from "@/lib/css";
import { siteName } from "@/lib/report-view";
import { useBriefRuns } from "@/lib/use-brief-runs";

export type FromBrief = { id: string; brief: Brief | null; site: string | null };

// The brief this run came from, read once. Until it loads (or if it can't be read) only its id is known.
export function useFromBrief(briefId: string | null | undefined): FromBrief | null {
  const [loaded, setLoaded] = useState<{ id: string; run: BriefRun } | null>(null);
  useEffect(() => {
    if (!briefId) return;
    let cancelled = false;
    fetch(`/api/briefs/${encodeURIComponent(briefId)}`, { cache: "no-store" })
      .then((response) => (response.ok ? (response.json() as Promise<{ run: BriefRun }>) : null))
      .then((body) => {
        if (!cancelled && body?.run) setLoaded({ id: briefId, run: body.run });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [briefId]);
  if (!briefId) return null;
  const run = loaded?.id === briefId ? loaded.run : null;
  return {
    id: briefId,
    brief: run && isBrief(run.brief) ? run.brief : null,
    site: run ? siteName(run.url) : null,
  };
}

export function BriefBacklink({ from }: { from: FromBrief }) {
  return (
    <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-ink2">
      <span>
        From your brief of <span className="font-semibold text-ink">{from.site ?? "this site"}</span>
      </span>
      <Link href={`/brief/${from.id}`} className="fu-link font-semibold">
        ← Back to brief
      </Link>
    </p>
  );
}

export function TestAnotherJourney({ from }: { from: FromBrief }) {
  const runs = useBriefRuns(from.brief ? from.id : null);
  // Waits for the list of tests, so a journey already tested never shows for a moment.
  if (!from.brief || !runs) return null;
  const brief = from.brief;
  const left = untestedJourneys(brief.suggested_journeys ?? [], runs);
  return (
    <section aria-labelledby="fu-r-another" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <h2 id="fu-r-another" className="fu-display fu-display-wide text-card" style={{ lineHeight: 1 }}>
          Test another journey
        </h2>
        <span className="text-[15px] text-ink2">
          {left.length > 0 ? (
            <>From the brief of {siteName(brief.url)}, not tested yet.</>
          ) : (
            <>
              Every journey the brief suggested has been tested.{" "}
              <Link href={`/brief/${from.id}`} className="fu-link font-semibold">
                See them on the brief
              </Link>
              .
            </>
          )}
        </span>
      </div>
      {left.length > 0 && (
        <ul className="fu-grid m-0 list-none p-0" style={grid("260px", "12px")}>
          {left.map((journey, index) => (
            <li key={`${index}-${journey.goal}`} className="fu-card-sm flex flex-col gap-3 p-[18px]">
              <span className="text-[16px] font-semibold leading-snug [overflow-wrap:anywhere]">{journey.goal}</span>
              {journey.success && <span className="text-[14px] leading-normal text-ink2">Success looks like: {journey.success}</span>}
              <Link href={testJourneyHref(from.id, brief.url, journey.goal, journey.success)} className="fu-btn mt-auto">
                Test this journey →
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
