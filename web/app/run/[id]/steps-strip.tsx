// "The whole run": every step as a card in a sideways strip, with its screenshot, what the visitor did,
// its own thought and what happened. Each card is the target of the report's "step N" links.

import { describeAction, isHttpUrl, pathOf, stepStatus, type StepTone } from "@/lib/report-view";
import type { Step } from "@/lib/types";

const TONE: Record<StepTone, { bg: string; fg: string }> = {
  done: { bg: "var(--green-soft)", fg: "var(--green-ink)" },
  retry: { bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  problem: { bg: "var(--bad)", fg: "var(--on-bad)" },
  ours: { bg: "var(--s2)", fg: "var(--ink2)" },
  end: { bg: "var(--acc)", fg: "var(--on-acc)" },
  blocked: { bg: "var(--blue-soft)", fg: "var(--blue-ink)" },
};

// Which try of the worker's recovery ladder changed the page (see worker/tools.py do()).
const RETRY_WORDING: Record<string, string> = {
  b: "Worked on the second try, after our browser tool looked for the element again.",
  c: "Worked on the third try, with a direct click on the element.",
  d: "Worked on the fourth try, with a real mouse click.",
};

// The worker caps summaries at this length; older runs cut them mid-word.
const SUMMARY_LIMIT = 400;

function tidySummary(summary: string): string {
  const trimmed = summary.trim();
  if (summary.length < SUMMARY_LIMIT || /[.!?…)"']$/.test(trimmed)) return trimmed;
  const lastSpace = trimmed.lastIndexOf(" ");
  const cut = lastSpace > SUMMARY_LIMIT / 2 ? trimmed.slice(0, lastSpace) : trimmed;
  return `${cut.replace(/[\s,;:-]+$/, "")}…`;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function describeResult(step: Step): string | null {
  const result = step.result ?? {};
  const input = step.input ?? {};
  if (result.error) return "The browser tool hit an error on this step.";
  switch (step.tool) {
    case "look":
      return result.unchanged ? "Nothing had changed since the last look." : tidySummary(text(result.summary)) || null;
    case "do":
      if (result.success) return RETRY_WORDING[text(result.rung)] ?? "It worked.";
      return "Nothing happened. Our browser tool may have failed here, so this is logged as our issue.";
    case "note_friction":
      return `Expected: ${text(input.expected)} What happened: ${text(input.happened)}`;
    case "finish":
      return text(input.reason) || null;
    default:
      return null;
  }
}

export function StepsStrip({ steps, highlight, live = false }: { steps: Step[]; highlight: Set<number>; live?: boolean }) {
  return (
    <section id="fu-r-steps" aria-labelledby="steps-title" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2.5">
        <div className="flex flex-col gap-2.5">
          <span className="fu-eyebrow">{live ? "Steps so far" : "03 · Every step"}</span>
          <h2 id="steps-title" className="fu-display fu-display-mid text-block" style={{ lineHeight: 0.95 }}>
            The whole run
          </h2>
        </div>
        <span className="font-code text-[13px] font-medium text-ink3">Scroll sideways →</span>
      </div>
      {steps.length === 0 ? (
        <p className="m-0 text-[15px] text-ink2">No steps were recorded.</p>
      ) : (
        <ol className="fu-scroll-x m-0 list-none" tabIndex={0} aria-label="Steps of the visit">
          {steps.map((step) => {
            const status = stepStatus(step);
            const tone = TONE[status.tone];
            const flagged = highlight.has(step.idx);
            const result = describeResult(step);
            return (
              <li
                key={step.idx}
                id={`step-${step.idx}`}
                className="flex w-[240px] flex-none snap-start scroll-mt-28 flex-col overflow-hidden rounded-frame bg-s1 transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-[5px_5px_0_var(--hard)]"
                style={{ border: `1.5px solid ${flagged ? "var(--bad)" : "var(--line)"}` }}
              >
                {isHttpUrl(step.screenshot_path) ? (
                  <a href={step.screenshot_path} target="_blank" rel="noopener noreferrer" className="block border-b border-line bg-page">
                    {/* Screenshots are stored in Supabase Storage; a plain img avoids configuring remote image hosts. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={step.screenshot_path}
                      alt={`The page after step ${step.idx}`}
                      loading="lazy"
                      className="block aspect-[16/10] w-full object-cover object-top"
                    />
                  </a>
                ) : (
                  <div aria-hidden className="flex aspect-[16/10] flex-col gap-[5px] border-b border-line bg-page p-2">
                    <span className="truncate font-code text-[9px] font-medium text-page-ink4">{pathOf(step.url) || "/"}</span>
                    <span className="h-1.5 w-1/2 rounded-sm bg-page-ink2" />
                    <span className="h-4 rounded border border-page-line" />
                    <span className="h-4 w-[46%] self-start rounded bg-page-btn" />
                  </div>
                )}
                <div className="flex flex-1 flex-col gap-1.5 px-3 pb-3 pt-2.5">
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="font-code text-[11px] font-medium text-ink3">Step {step.idx}</span>
                    <span
                      className="flex h-5 items-center whitespace-nowrap rounded-pill px-[7px] text-[10px] font-semibold"
                      style={{ background: tone.bg, color: tone.fg }}
                    >
                      {status.label}
                    </span>
                  </div>
                  <span className="text-[14px] font-medium leading-[1.35] [overflow-wrap:anywhere]">{describeAction(step)}</span>
                  {step.thought && (
                    <span className="line-clamp-3 border-l-2 border-line pl-2 text-[12px] italic leading-[1.4] text-ink3" title={step.thought}>
                      {step.thought}
                    </span>
                  )}
                  {result && (
                    <span className="line-clamp-4 text-[12px] leading-[1.4] text-ink2" title={result}>
                      {result}
                    </span>
                  )}
                  {step.url && <span className="mt-auto truncate font-code text-[11px] text-ink4">{pathOf(step.url) || "/"}</span>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
