"use client";

// "04 · Transparency": how this report was made, laid out for scanning. Four stat tiles, then grouped facts. The run
// facts are counted from the run, none of them is written by a model; the way in is read from what the visit
// recorded. With the facts switched off (NEXT_PUBLIC_REPORT_V2_FACTS), only the tiles and the way in show, as
// before Report v2. Open by default on a wide screen, collapsed on a phone.

import { useState, type ReactNode } from "react";

import { formatSeconds, runSeconds } from "@/lib/report-view";
import type { Run, RunFacts, Step } from "@/lib/types";

import { copyText } from "../../copy";
import { formatCost, wayInLines } from "./report-bits";

const CHECK: Record<string, { label: string; bg: string; fg: string }> = {
  verified: { label: "Verified", bg: "var(--green-soft)", fg: "var(--green-ink)" },
  contradicted: { label: "Contradicted", bg: "var(--bad-soft)", fg: "var(--bad-ink)" },
  unverified: { label: "Unverified", bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
};

function None({ children = "None" }: { children?: ReactNode }) {
  return <span className="text-ink4">{children}</span>;
}

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-panel border border-line bg-bg px-4 py-3.5">
      <span className="fu-eyebrow-sm">{label}</span>
      <span className="text-[22px] font-semibold leading-tight tabular-nums">{children}</span>
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1 border-t border-line pt-4">
      <h3 className="m-0 mb-1 text-[16px] font-semibold">{title}</h3>
      <dl className="m-0 flex flex-col">{children}</dl>
    </section>
  );
}

// One label and its value, side by side on a wide screen and stacked on a phone.
function Row({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="grid gap-x-6 gap-y-0.5 py-2 @min-[700px]:grid-cols-[200px_minmax(0,1fr)]">
      <dt className="text-[14px] text-ink3">{label}</dt>
      <dd className={`m-0 leading-normal [overflow-wrap:anywhere] ${mono ? "font-code text-[14px]" : "text-[15px]"}`}>{children}</dd>
    </div>
  );
}

function List({ items, mono = false }: { items: string[]; mono?: boolean }) {
  return (
    <ul className={`m-0 flex list-none flex-col gap-1 p-0 ${mono ? "font-code text-[13px]" : ""}`}>
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

function TraceId({ id }: { id: string }) {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <span className="flex flex-wrap items-center gap-2">
      <code className="[overflow-wrap:anywhere]">{id}</code>
      <button
        type="button"
        onClick={async () => {
          setCopied((await copyText(id)) ? "copied" : "failed");
          setTimeout(() => setCopied("idle"), 1600);
        }}
        className="fu-btn fu-btn-ghost h-8 px-3 font-sans text-[13px]"
      >
        <span aria-live="polite">{copied === "copied" ? "Copied ✓" : copied === "failed" ? "Couldn't copy" : "Copy"}</span>
      </button>
    </span>
  );
}

export function HowMade({ run, steps, showFacts }: { run: Run; steps: Step[]; showFacts: boolean }) {
  const facts: RunFacts | null = showFacts ? run.run_facts : null;
  // The report renders only in the browser, after the run is fetched, so the screen width is known here.
  const [open, setOpen] = useState(() => typeof window !== "undefined" && window.matchMedia("(min-width: 700px)").matches);
  const check = facts?.verifier?.verdict ? CHECK[facts.verifier.verdict] : null;

  return (
    <details
      id="fu-r-made"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="overflow-hidden rounded-card border-[1.5px] border-ink bg-s1"
    >
      <summary className="flex min-h-[72px] items-center justify-between gap-4 px-6 py-[18px]">
        <span className="flex flex-col gap-1">
          <span className="fu-eyebrow-sm">04 · Transparency</span>
          <span className="text-[19px] font-semibold">How this report was made</span>
        </span>
        <span aria-hidden className="fu-plus size-9">
          +
        </span>
      </summary>
      <div className="flex flex-col gap-5 px-6 pb-6">
        <div className="grid grid-cols-2 gap-2.5 @min-[700px]:grid-cols-4">
          <Tile label="Steps">{facts?.steps_taken ?? steps.length}</Tile>
          <Tile label="Duration">{formatSeconds(runSeconds(run))}</Tile>
          <Tile label="Cost">{formatCost(facts?.cost_usd ?? run.cost_usd)}</Tile>
          <Tile label="Independent check">
            {check ? (
              <span className="inline-flex h-7 items-center rounded-pill px-2.5 text-[13px] font-semibold" style={{ background: check.bg, color: check.fg }}>
                {check.label}
              </span>
            ) : facts ? (
              <span className="text-[15px] font-medium text-ink4">Not run</span>
            ) : (
              <span className="text-[15px] font-medium text-ink4">Not recorded</span>
            )}
          </Tile>
        </div>

        <Group title="How the visitor got in">
          <Row label="Way in">
            <List items={wayInLines(run)} />
          </Row>
        </Group>

        {showFacts && !facts && (
          <p className="m-0 border-t border-line pt-4 text-[15px] text-ink4">
            The detailed facts were not recorded for this run: it was made before they were.
          </p>
        )}

        {facts && (
          <>
            <Group title="What happened">
              <Row label="Recoveries">
                {facts.recoveries.length === 0 ? (
                  <None />
                ) : (
                  <List items={facts.recoveries.map((r) => `Step ${r.step}: rung ${r.rung} (${r.how})`)} />
                )}
              </Row>
              <Row label="Our own issues">
                {facts.own_issues.length === 0 ? (
                  <None />
                ) : (
                  <>
                    <List items={facts.own_issues.map((issue) => (issue.step !== null ? `Step ${issue.step}` : "A step"))} />
                    <span className="text-[13px] text-ink3">Our browser tool had no effect; not the site&apos;s fault.</span>
                  </>
                )}
              </Row>
              <Row label="Page reloads">{facts.page_reloads === 0 ? <None /> : facts.page_reloads}</Row>
              <Row label="Hidden page errors">
                {facts.page_error_count === 0 ? (
                  <None />
                ) : (
                  <>
                    <List
                      mono
                      items={[
                        ...facts.page_errors,
                        ...(facts.page_error_count > facts.page_errors.length
                          ? [`and ${facts.page_error_count - facts.page_errors.length} more`]
                          : []),
                      ]}
                    />
                  </>
                )}
              </Row>
            </Group>

            <Group title="How we checked">
              <Row label="Independent check">
                {facts.verifier ? (
                  <span className="flex flex-col gap-1.5">
                    {check && (
                      <span className="inline-flex h-6 items-center self-start rounded-pill px-2 text-[12px] font-semibold" style={{ background: check.bg, color: check.fg }}>
                        {check.label}
                      </span>
                    )}
                    <span className="border-l-2 border-line pl-3 text-ink2">{facts.verifier.quote}</span>
                  </span>
                ) : (
                  <None>Not run: the visitor did not claim to reach the goal</None>
                )}
              </Row>
              <Row label="Success condition">
                {facts.success_condition ?? <None>None given: the goal was checked as worded</None>}
              </Row>
            </Group>

            <Group title="For engineers">
              <Row label="Agent version" mono>
                {facts.agent_version ?? <None>Not recorded</None>}
              </Row>
              <Row label="Worker" mono>
                {facts.worker_id ?? <None>Not recorded</None>}
              </Row>
              <Row label="neatlogs trace ID" mono>
                {facts.trace_id ? <TraceId id={facts.trace_id} /> : <None>Not recorded</None>}
              </Row>
            </Group>
          </>
        )}

        <p className="m-0 border-t border-line pt-4 text-[13px] leading-normal text-ink3">
          The visit is a simulated user, so treat findings as leads to check. Recommendations are our suggestions and
          promise no outcome.
        </p>
      </div>
    </details>
  );
}
