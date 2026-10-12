"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { BRIEF_PHASES, BRIEF_STALL_MS, type BriefPhase } from "@/lib/brief-logic";
import { grid } from "@/lib/css";
import { idFromPath, parsePendingRun, pendingRunSnapshot } from "@/lib/pending-run";
import { siteName } from "@/lib/report-view";

const LABEL: Record<BriefPhase, string> = {
  queued: "Queued",
  reading: "Reading the site's pages",
  writing: "Writing the brief",
  done: "Done",
};

// The brief page while the brief is being made: where it is, the address being read, and the shape of the
// journeys to come. Shown from the moment the run is queued (the form remembers the address), so the visitor
// never waits on a blank page.
export function BriefWaiting({ url, phase, pagesRead }: { url: string; phase: BriefPhase; pagesRead: number | null }) {
  const current = BRIEF_PHASES.indexOf(phase);
  const site = url ? siteName(url) : "";
  return (
    <>
      <div className="flex min-w-0 flex-col gap-2.5">
        <span className="fu-eyebrow">Understand{site && <> · {site}</>}</span>
        <h1 className="fu-display text-pagetitle" style={{ overflowWrap: "anywhere" }}>
          {site || "Reading the site"}
        </h1>
      </div>

      <section aria-labelledby="brief-waiting-title" aria-busy className="fu-card-sm flex flex-col gap-4 p-6">
        <div className="flex flex-col gap-1.5">
          <h2 id="brief-waiting-title" className="m-0 flex items-center gap-2 font-code text-[12px] font-medium uppercase tracking-[.06em] text-ink3">
            <span
              aria-hidden
              className="size-2 flex-none rounded-full"
              style={{ background: phase === "queued" ? "var(--ink4)" : "var(--pass)", animation: "fuBlink 1.6s ease-in-out infinite" }}
            />
            Writing your brief
          </h2>
          {url && (
            <p className="m-0 text-[15px] text-ink2">
              Reading <span className="font-code text-[14px] text-ink [overflow-wrap:anywhere]">{url}</span>
            </p>
          )}
        </div>
        <p role="status" className="sr-only">
          {LABEL[phase]}
          {phase === "reading" && pagesRead !== null ? `, ${pagesRead} page${pagesRead === 1 ? "" : "s"} read` : ""}
        </p>
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {BRIEF_PHASES.map((step, index) => {
            const state = index < current ? "done" : index === current ? "now" : "next";
            const count = step === "reading" && pagesRead !== null && index <= current;
            return (
              <li key={step} className="flex items-center gap-3 text-[15px]" aria-current={state === "now" ? "step" : undefined}>
                <span
                  aria-hidden
                  className="flex size-6 flex-none items-center justify-center rounded-full border-[1.5px] text-[12px] font-semibold"
                  style={{
                    borderColor: state === "next" ? "var(--line)" : "var(--ink)",
                    background: state === "done" ? "var(--ink)" : state === "now" ? "var(--acc)" : "transparent",
                    color: state === "done" ? "var(--bg)" : state === "now" ? "#0E1320" : "var(--ink)",
                  }}
                >
                  {state === "done" ? "✓" : index + 1}
                </span>
                <span className={state === "next" ? "text-ink3" : state === "now" ? "font-semibold text-ink" : "text-ink2"}>
                  {LABEL[step]}
                  {count && (
                    <span className="font-normal text-ink3">
                      {" "}
                      · {pagesRead} page{pagesRead === 1 ? "" : "s"} read
                    </span>
                  )}
                  <span className="sr-only">{state === "done" ? " (finished)" : state === "now" ? " (in progress)" : ""}</span>
                </span>
              </li>
            );
          })}
        </ol>
        {/* Keyed by where the run is: anything new starts the 90 seconds again. */}
        <StillReading key={`${phase}:${pagesRead ?? ""}`} />
        <p className="m-0 text-[14px] leading-normal text-ink3">
          This page updates by itself, and you can come back to this link later.
        </p>
      </section>

      <JourneysSkeleton />
    </>
  );
}

const noSubscription = () => () => {};

// The whole page before the brief page's code and first answer arrive (the route's loading state): the run
// is queued, and the address is the one the form remembered, when there is one.
export function BriefLoading() {
  const pending = parsePendingRun(useSyncExternalStore(noSubscription, () => pendingRunSnapshot(idFromPath()), () => null));
  return (
    <main className="fu-page" style={{ gap: "clamp(28px,4cqi,40px)" }}>
      <BriefWaiting url={pending?.url ?? ""} phase="queued" pagesRead={null} />
    </main>
  );
}

function StillReading() {
  const [stalled, setStalled] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setStalled(true), BRIEF_STALL_MS);
    return () => clearTimeout(timer);
  }, []);
  if (!stalled) return null;
  return <p className="fu-notice m-0">Still reading. Briefs usually take under two minutes.</p>;
}

function JourneysSkeleton() {
  return (
    <section aria-label="Suggested journeys, still being written" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <h2 className="fu-display fu-display-wide text-card text-ink3" style={{ lineHeight: 1 }}>
          Suggested journeys
        </h2>
        <span className="text-[15px] text-ink3">They appear here when the brief is written, each one ready to test.</span>
      </div>
      <ol aria-hidden className="fu-grid m-0 list-none p-0" style={grid("280px")}>
        {[0, 1, 2].map((index) => (
          <li key={index} className="fu-card-sm flex flex-col gap-3.5 p-5">
            <span className="font-code text-[12px] font-medium text-ink4">{String(index + 1).padStart(2, "0")}</span>
            <span className="fu-skeleton-ui h-3 w-16" />
            <span className="fu-skeleton-ui h-11" />
            <span className="fu-skeleton-ui h-3 w-24" />
            <span className="fu-skeleton-ui h-11" />
            <span className="fu-skeleton-ui mt-2 h-11 rounded-pill" />
          </li>
        ))}
      </ol>
    </section>
  );
}
