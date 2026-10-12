"use client";

// A run on its way: the six phases, the step count, the latest screenshot (or a skeleton of it) and one calm line
// about what is happening now, all from what the worker has saved so far (lib/report-view.ts liveState). It also
// shows before the first response, from what the form remembered, so the page is never blank. The page polls,
// so this updates by itself.

import { useEffect, useState } from "react";

import { LIVE_PHASES, MAX_STEPS, PHASE_LINES, liveState, siteName } from "@/lib/report-view";
import type { Run, Step } from "@/lib/types";

const STALL_MS = 90_000;

// Shown when nothing has changed for 90 seconds. Remounted (by key) whenever something changes.
function StallNotice() {
  const [stalled, setStalled] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setStalled(true), STALL_MS);
    return () => clearTimeout(timer);
  }, []);
  if (!stalled) return null;
  return (
    <p role="status" className="fu-notice m-0">
      Still working. Runs usually take a few minutes.
    </p>
  );
}

export function LiveRun({
  run,
  steps,
  pending,
  id,
}: {
  run: Run | null;
  steps: Step[];
  pending?: { url: string; goal: string } | null;
  // The run's id from the address, shown before the first response too.
  id?: string;
}) {
  // Before the first response the run is treated as queued: that is where every new run starts.
  const live = run ? liveState(run, steps) : liveState({ status: "queued", first_impression: null }, []);
  const url = run?.url ?? pending?.url ?? "";
  const goal = run?.goal ?? pending?.goal ?? "";
  const waiting = !run;
  // Queue position: the runs API does not report one, so a queued run says it is waiting for a free browser.
  const line = waiting ? "Getting your run ready" : live.action;
  const signature = `${run?.status ?? "loading"}:${steps.length}:${run?.first_impression ? 1 : 0}`;

  return (
    <section aria-labelledby="live-title" aria-busy className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2.5">
          <span className="flex items-center gap-2 font-code text-[12px] font-medium uppercase tracking-[.06em] text-ink3">
            <span
              aria-hidden
              className="size-2 rounded-full"
              style={{ background: live.queued ? "var(--ink4)" : "var(--pass)", animation: "fuBlink 1.6s ease-in-out infinite" }}
            />
            {live.queued ? "Queued" : "Running"}
            {url && <> · {siteName(url)}</>}
          </span>
          {goal ? (
            <h1 id="live-title" className="fu-display text-run" style={{ lineHeight: 0.9, overflowWrap: "anywhere" }}>
              {goal}
            </h1>
          ) : (
            <h1 id="live-title" className="fu-display text-run" style={{ lineHeight: 0.9 }}>
              Starting your run
            </h1>
          )}
          {url && <span className="font-code text-[13px] text-ink3 [overflow-wrap:anywhere]">{url}</span>}
          {(run?.id ?? id) && (
            <span className="font-code text-[12px] text-ink3" title={run?.id ?? id}>
              Run {(run?.id ?? id ?? "").slice(0, 8)}
            </span>
          )}
        </div>
        <span className="whitespace-nowrap font-code text-[15px] font-medium">
          Step {live.stepCount} of up to {MAX_STEPS}
        </span>
      </div>

      <ol className="m-0 grid list-none gap-2 p-0" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,150px),1fr))" }}>
        {LIVE_PHASES.map((name, i) => {
          const done = live.phase > i;
          const on = live.phase === i;
          return (
            <li
              key={name}
              aria-current={on ? "step" : undefined}
              className="flex items-center gap-2.5 rounded-field px-3.5 py-3"
              style={{
                border: `1.5px solid ${on ? "var(--ink)" : "var(--line)"}`,
                background: on ? "var(--acc-soft)" : "var(--s1)",
                transition: "background .6s, border-color .6s",
              }}
            >
              <span
                aria-hidden
                className="flex size-6 flex-none items-center justify-center rounded-full border-[1.5px] border-ink text-[12px] font-semibold"
                style={{ background: done ? "var(--acc)" : on ? "var(--s1)" : "var(--s2)", color: done ? "#0E1320" : "var(--ink)" }}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className="text-[14px] font-medium leading-[1.3]" style={{ color: done || on ? "var(--ink)" : "var(--ink3)" }}>
                {name}
                <span className="sr-only">{done ? " (done)" : on ? " (now)" : ""}</span>
              </span>
            </li>
          );
        })}
      </ol>

      <div className="overflow-hidden rounded-cardsm border-[1.5px] border-ink bg-s1 shadow-hard-lg">
        <div className="flex items-center gap-2.5 border-b border-line bg-s2 px-3.5 py-2.5">
          <span aria-hidden className="fu-traffic">
            <span />
            <span />
            <span />
          </span>
          <span className="flex h-7 min-w-0 flex-1 items-center overflow-hidden whitespace-nowrap rounded-r8 border border-line bg-s1 px-3 font-code text-[12px] font-medium text-ink3">
            <span className="truncate">{live.pageUrl ?? run?.start_url ?? url}</span>
          </span>
          <span className="whitespace-nowrap font-code text-[11px] font-medium text-ink3">
            {live.screenshot ? `Latest screenshot · step ${live.screenshot.step}` : "Latest screenshot"}
          </span>
        </div>
        {live.screenshot ? (
          <div className="bg-page">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={live.screenshot.url} alt={`The page at step ${live.screenshot.step}`} className="fu-browser-shot" />
          </div>
        ) : (
          <div aria-hidden className="grid aspect-video min-h-[240px] bg-page" style={{ gridTemplateColumns: "minmax(70px,20%) minmax(0,1fr)" }}>
            <div className="flex flex-col gap-2.5 border-r border-page-line bg-page-side px-3 py-4">
              <span className="fu-skeleton h-3 w-[60%]" />
              <span className="fu-skeleton h-2 w-[75%]" />
              <span className="fu-skeleton h-2 w-[55%]" />
              <span className="fu-skeleton h-2 w-[65%]" />
            </div>
            <div className="flex min-w-0 flex-col gap-3" style={{ padding: "clamp(14px,3cqi,32px)" }}>
              <span className="fu-skeleton h-6 w-[55%]" />
              <span className="fu-skeleton h-9 w-full" />
              <span className="fu-skeleton h-9 w-[80%]" />
              <span className="fu-skeleton h-9 w-32" />
            </div>
          </div>
        )}
        <div className="flex items-center gap-3.5 border-t-[1.5px] border-ink px-[18px] py-4">
          <span className="flex h-[26px] flex-none items-center rounded-pill bg-deep px-2.5 font-code text-[11px] font-medium tracking-[.06em] text-acc-fixed">
            NOW
          </span>
          <span role="status" className="min-w-0 flex-1 truncate text-[clamp(16px,1.8cqi,19px)] font-medium leading-[1.35]" title={line}>
            {line}
          </span>
        </div>
      </div>
      <StallNotice key={signature} />
      <p className="m-0 text-[14px] text-ink3">
        {waiting || live.queued ? PHASE_LINES[0] + ". " : ""}A run takes a few minutes. You can leave this page; the report keeps its
        link.
      </p>
    </section>
  );
}
