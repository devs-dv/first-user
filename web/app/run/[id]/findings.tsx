"use client";

// The report's ranked problems, most likely to stop a new user first, each with evidence and a prompt to
// paste into a coding agent; then what the visitor noted that did not become a finding, and our own issues.

import { useState, type ReactNode } from "react";

import { grid } from "@/lib/css";
import { feedbackShown, findingIds } from "@/lib/feedback-logic";
import type { ReportFlags } from "@/lib/report-flags";
import { frictionsNotInFindings } from "@/lib/report-logic";
import { fixPromptParts, isHttpUrl } from "@/lib/report-view";
import type { Finding, Friction, Run, VerdictKind } from "@/lib/types";

import { copyText } from "../../copy";
import { FindingFeedback } from "./finding-feedback";
import { BasisBadge } from "./report-v2";
import { BrowserFrame } from "./report-bits";

const SEVERITY: Record<Finding["severity"], { label: string; bg: string; fg: string }> = {
  high: { label: "High", bg: "var(--bad)", fg: "var(--on-bad)" },
  medium: { label: "Medium", bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  low: { label: "Low", bg: "var(--s2)", fg: "var(--ink2)" },
};

const KIND: Record<Finding["kind"], string> = {
  site_problem: "Site problem",
  unclear_wording: "Unclear wording",
  hidden_error: "Hidden error",
};

const MAX_FINDINGS = 5;

export function Findings({ run, flags, kind }: { run: Run; flags: ReportFlags; kind: VerdictKind }) {
  const findings = run.findings;
  if (findings === null) return null; // from before the report writer, or it could not be written
  // The same ids the feedback route uses, so a vote lands on the right finding.
  const ids = findingIds(findings);
  const showFeedback = flags.feedback && feedbackShown(run);
  const empty =
    kind === "bot_check"
      ? "No findings. A bot check stopped the run before the visitor saw your product."
      : kind === "our_failure"
        ? "No findings. The run failed on our side, so nothing here is about your site."
        : "Nothing in this visit stood out as a problem with your site.";
  return (
    <section id="fu-r-find" aria-labelledby="findings-title" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2.5">
        <div className="flex flex-col gap-2.5">
          <span className="fu-eyebrow">02 · Findings</span>
          <h2 id="findings-title" className="fu-display fu-display-mid text-block" style={{ lineHeight: 0.95 }}>
            What to fix
          </h2>
        </div>
        {findings.length > 0 && (
          <span className="font-code text-[13px] font-medium text-ink3">
            {findings.length} of up to {MAX_FINDINGS} · ranked by how likely each is to stop a new user
          </span>
        )}
      </div>
      {findings.length === 0 ? (
        <div className="rounded-cardsm border-[1.5px] border-dashed border-ink3 p-6 text-[16px] leading-normal text-ink2">{empty}</div>
      ) : (
        <ol className="m-0 flex list-none flex-col gap-4 p-0">
          {findings.map((finding, index) => (
            <FindingCard
              key={index}
              finding={finding}
              rank={index + 1}
              flags={flags}
              feedback={showFeedback && <FindingFeedback runId={run.id} findingId={ids[index]} checkAgain={flags.checkAgain} />}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

type CopyState = "idle" | "copied" | "failed";

function FindingCard({ finding, rank, flags, feedback }: { finding: Finding; rank: number; flags: ReportFlags; feedback?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [copy, setCopy] = useState<CopyState>("idle");
  const evidence = finding.evidence;
  const severity = SEVERITY[finding.severity] ?? SEVERITY.low;
  const seen = finding.also_seen_at ?? [];
  const panelId = `fix-${rank}`;

  async function copyPrompt() {
    const ok = await copyText(finding.fix_prompt);
    setCopy(ok ? "copied" : "failed");
    setOpen(true);
    setTimeout(() => setCopy((state) => (state === "copied" ? "idle" : state)), 1800);
  }

  return (
    <li className="fu-card fu-lift fu-lift-sm overflow-hidden">
      <div className="fu-grid" style={grid("320px", "20px clamp(20px,3cqi,32px)", { padding: "var(--card-pad)" })}>
        <div className="flex flex-col gap-3.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1.5 font-display text-[28px] font-[850] leading-none" style={{ fontStretch: "70%" }}>
              {String(rank).padStart(2, "0")}
            </span>
            <span className="fu-chip fu-chip-word" style={{ background: severity.bg, color: severity.fg }}>
              {severity.label}
            </span>
            {finding.basis && <BasisBadge basis="observed" show={flags.labels} short />}
            <span className="fu-chip fu-chip-tag">{KIND[finding.kind] ?? finding.kind}</span>
          </div>
          <h3 className="m-0 text-[clamp(19px,2cqi,23px)] font-semibold leading-[1.3] fu-pretty">{finding.title}</h3>
          <div className="fu-grid" style={grid("200px", "10px")}>
            <div className="fu-panel bg-s2">
              <span className="fu-eyebrow-sm">Expected</span>
              <span className="text-[15px] leading-normal">{finding.expected}</span>
            </div>
            <div className="fu-panel bg-bad-soft">
              <span className="fu-eyebrow-sm text-bad-ink">What happened</span>
              <span className="text-[15px] leading-normal">{finding.happened}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-2.5">
          <a href={`#step-${evidence.step}`} className="fu-eyebrow-sm hover:text-ink">
            Evidence · step {evidence.step}
          </a>
          <BrowserFrame url={evidence.url}>
            {isHttpUrl(evidence.screenshot_url) ? (
              <a href={evidence.screenshot_url} target="_blank" rel="noopener noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={evidence.screenshot_url} alt={`The page at step ${evidence.step}`} loading="lazy" className="fu-browser-shot" />
              </a>
            ) : (
              <p className="m-0 p-4 text-[13px] text-page-ink3">No screenshot was captured for this step.</p>
            )}
          </BrowserFrame>
          {seen.length > 0 && (
            <span className="text-[13px] text-ink2">
              Seen again at{" "}
              {seen.map((item, index) => (
                <span key={item.step}>
                  {index > 0 && ", "}
                  <a href={`#step-${item.step}`} className="fu-link">
                    step {item.step}
                  </a>
                </span>
              ))}
            </span>
          )}
          {evidence.quote && (
            <span className="text-[13px] leading-normal text-ink2">
              The page said: &ldquo;{evidence.quote}&rdquo;
            </span>
          )}
          {evidence.page_errors.length > 0 && (
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {evidence.page_errors.map((error, index) => (
                <li key={index} className="font-code text-[12px] leading-normal text-bad-ink [overflow-wrap:anywhere]">
                  {error}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-line bg-s2" style={{ padding: "12px var(--card-pad)" }}>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={copyPrompt} aria-controls={panelId} aria-expanded={open} className="fu-btn text-[14px]">
            {copy === "copied" ? "Copied ✓" : open ? "Copy fix prompt again" : "Copy fix prompt"}
          </button>
          <button type="button" onClick={() => setOpen(!open)} aria-controls={panelId} aria-expanded={open} className="fu-text-btn px-2 text-[14px] text-ink2">
            {open ? "Hide the prompt" : "Show the prompt"}
          </button>
        </div>
        {feedback}
      </div>
      {open && <FixPanel id={panelId} finding={finding} flags={flags} copy={copy} />}
    </li>
  );
}

// The fix prompt in its parts, on the dark panel of the design. Acceptance criteria can be ticked off.
function FixPanel({ id, finding, flags, copy }: { id: string; finding: Finding; flags: ReportFlags; copy: CopyState }) {
  const parts = fixPromptParts(finding.fix_prompt);
  const criteria = flags.criteria ? (finding.acceptance_criteria ?? []) : [];
  // The criteria are listed once: from the finding when the flag shows them, else from the prompt.
  const shown = criteria.length > 0 ? parts.filter((part) => part.kind !== "criteria") : parts;
  const hasReproduce = /steps to reproduce/i.test(finding.fix_prompt);
  return (
    <div id={id} className="fu-code fu-grid" style={grid("260px", "18px 28px", { padding: "var(--card-pad)" })}>
      <span className="fu-code-title flex flex-wrap items-center gap-2" style={{ gridColumn: "1/-1" }} aria-live="polite">
        {copy === "copied" ? "Fix prompt · copied to clipboard" : copy === "failed" ? "Fix prompt · couldn't copy, select the text below" : "Fix prompt"}
        {flags.labels && (
          <span className="rounded-pill border border-dashed border-current px-2 py-0.5 text-[11px] normal-case tracking-normal">Our recommendation</span>
        )}
      </span>
      {shown.map((part, index) => (
        <div key={index} className="flex min-w-0 flex-col gap-1">
          <span className="fu-code-h">{part.heading}</span>
          {part.kind === "criteria" ? (
            <Criteria items={part.lines} />
          ) : (
            part.lines.map((line, lineIndex) => (
              <span key={lineIndex} className="whitespace-pre-wrap [overflow-wrap:anywhere]">
                {line}
              </span>
            ))
          )}
        </div>
      ))}
      {criteria.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="fu-code-h">Acceptance criteria</span>
          <Criteria items={criteria} />
        </div>
      )}
      {!hasReproduce && finding.reproduce.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1">
          <span className="fu-code-h">Steps to reproduce</span>
          <ol className="m-0 flex flex-col gap-1 pl-5">
            {finding.reproduce.map((line, index) => (
              <li key={index} className="[overflow-wrap:anywhere]">
                {line}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function Criteria({ items }: { items: string[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item, index) => (
        <label key={index} className="flex cursor-pointer items-start gap-2.5">
          <input type="checkbox" className="mt-1 size-4 flex-none accent-[#C6FF3D]" />
          <span className="[overflow-wrap:anywhere]">{item}</span>
        </label>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------- also noted

export function Frictions({ frictions, findings }: { frictions: Friction[]; findings: Finding[] | null }) {
  // What became a finding is shown there, not again here.
  const noted = frictions.filter((f) => f.kind === "site");
  const site = frictionsNotInFindings(noted, findings);
  const inFindings = noted.length - site.length;
  const ours = frictions.filter((f) => f.kind === "agent_issue");
  return (
    <section aria-label="Also noted" className="fu-grid" style={grid("320px", "14px")}>
      <div className="flex flex-col gap-3 rounded-cardsm border-[1.5px] border-ink bg-s1 p-[22px]">
        <h3 className="m-0 text-[19px] font-semibold">Other problems the visitor noted</h3>
        {site.length === 0 ? (
          <p className="m-0 text-[15px] text-ink2">
            {inFindings > 0 ? "Everything the visitor noted is in the findings above." : "The visitor didn’t note any problems."}
          </p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {site.map((friction) => (
              <FrictionItem key={friction.id} friction={friction} />
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col gap-3 rounded-cardsm border-[1.5px] border-dashed border-ink3 p-[22px]">
        <h3 className="m-0 text-[19px] font-semibold">Our agent&apos;s own issues</h3>
        <p className="m-0 text-[14px] leading-normal text-ink3">
          Times our browser tool couldn&apos;t operate something. These are likely our fault, not your site&apos;s.
        </p>
        {ours.length === 0 ? (
          <p className="m-0 text-[15px] text-ink2">None.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {ours.map((friction) => (
              <FrictionItem key={friction.id} friction={friction} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function FrictionItem({ friction }: { friction: Friction }) {
  if (friction.kind === "agent_issue") {
    // The worker writes expected as "'<instruction>' changes the page"; show the instruction alone.
    const instruction = friction.expected?.match(/^'(.*)' changes the page$/)?.[1] ?? friction.expected;
    return (
      <li className="flex flex-col gap-1.5 border-t border-line pt-3 text-[15px] leading-normal">
        {friction.step_idx !== null && (
          <a href={`#step-${friction.step_idx}`} className="fu-eyebrow-sm hover:text-ink">
            Step {friction.step_idx}
          </a>
        )}
        {instruction && (
          <span>
            <span className="text-ink3">Tried to: </span>
            {instruction}
          </span>
        )}
        <span className="text-ink2">Nothing on the page changed after three different attempts.</span>
      </li>
    );
  }
  const severity = friction.severity ? SEVERITY[friction.severity] : null;
  return (
    <li className="flex flex-col gap-1.5 border-t border-line pt-3 text-[15px] leading-normal">
      <span className="flex flex-wrap items-center gap-2">
        {severity && (
          <span className="fu-chip fu-chip-word" style={{ background: severity.bg, color: severity.fg }}>
            {severity.label}
          </span>
        )}
        {friction.step_idx !== null && (
          <a href={`#step-${friction.step_idx}`} className="fu-eyebrow-sm hover:text-ink">
            Step {friction.step_idx}
          </a>
        )}
      </span>
      {friction.expected && (
        <span>
          <span className="text-ink3">Expected: </span>
          {friction.expected}
        </span>
      )}
      {friction.happened && (
        <span>
          <span className="text-ink3">What happened: </span>
          {friction.happened}
        </span>
      )}
    </li>
  );
}
