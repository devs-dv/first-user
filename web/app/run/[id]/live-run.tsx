// A run in progress: the four phases, the step count, the latest screenshot and what the visitor is doing
// now, all from what the worker has saved so far (lib/report-view.ts liveState). The page polls, so this
// updates by itself.

import { LIVE_PHASES, MAX_STEPS, liveState, siteName } from "@/lib/report-view";
import type { Run, Step } from "@/lib/types";


export function LiveRun({ run, steps }: { run: Run; steps: Step[] }) {
  const live = liveState(run, steps);
  return (
    <section aria-labelledby="live-title" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2.5">
          <span className="flex items-center gap-2 font-code text-[12px] font-medium uppercase tracking-[.06em] text-ink3">
            <span
              aria-hidden
              className="size-2 rounded-full"
              style={{ background: live.queued ? "var(--ink4)" : "var(--pass)", animation: "fuBlink 1.6s ease-in-out infinite" }}
            />
            {live.queued ? "In the queue" : "Live"} · {siteName(run.url)}
          </span>
          <h1 id="live-title" className="fu-display text-run" style={{ lineHeight: 0.9, overflowWrap: "anywhere" }}>
            {run.goal}
          </h1>
        </div>
        <span className="whitespace-nowrap font-code text-[15px] font-medium" aria-live="polite">
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
                style={{
                  background: done ? "var(--acc)" : on ? "var(--s1)" : "var(--s2)",
                  color: done ? "#0E1320" : "var(--ink)",
                }}
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
            <span className="truncate">{live.pageUrl ?? run.start_url ?? run.url}</span>
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
          <div className="flex aspect-video min-h-[240px] items-center justify-center bg-page p-6 text-center text-[15px] text-page-ink3">
            {live.queued ? "Waiting for a free browser. The first screenshot appears after the first action." : "The first screenshot appears after the first action."}
          </div>
        )}
        <div className="flex items-center gap-3.5 border-t-[1.5px] border-ink px-[18px] py-4">
          <span className="flex h-[26px] flex-none items-center rounded-pill bg-deep px-2.5 font-code text-[11px] font-medium tracking-[.06em] text-acc-fixed">
            NOW
          </span>
          <span role="status" className="min-w-0 flex-1 truncate text-[clamp(16px,1.8cqi,19px)] font-medium leading-[1.35]" title={live.action}>
            {live.action}
          </span>
        </div>
      </div>
      <p className="m-0 text-[14px] text-ink3">A run takes a few minutes. You can leave this page; the report keeps its link.</p>
    </section>
  );
}
