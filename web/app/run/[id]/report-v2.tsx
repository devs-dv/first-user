"use client";

// Report v2: the three answers, the verdict, the evidence labels and the run facts. Kept in its own file
// so the report page can show or hide each one by flag (lib/report-flags.ts).

import type { ReactNode } from "react";

import {
  BASIS_LABEL,
  BASIS_NOTE,
  fixFirst,
  shortUrl,
  understanding,
  withoutPromises,
} from "@/lib/report-logic";
import type { Basis, Run, RunFacts, Step, Verdict, VerdictKind } from "@/lib/types";

const BASIS_TONE: Record<Basis, string> = {
  observed: "border-line text-muted",
  verified: "border-success/30 bg-success-soft text-success",
  recommendation: "border-accent/40 text-accent",
};

// A small label saying what a statement rests on. Hidden with the labels flag.
export function BasisBadge({ basis, show = true }: { basis: Basis; show?: boolean }) {
  if (!show) return null;
  return (
    <span
      title={BASIS_NOTE[basis]}
      className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${BASIS_TONE[basis]}`}
    >
      {BASIS_LABEL[basis]}
    </span>
  );
}

const VERDICT_TONE: Record<VerdictKind, string> = {
  got_through: "border-success/30 bg-success-soft",
  unconfirmed: "border-warning/30 bg-warning-soft",
  stuck: "border-danger/30 bg-danger-soft",
  login_wall: "border-warning/30 bg-warning-soft",
  bot_check: "border-warning/30 bg-warning-soft",
  our_failure: "border-line bg-surface",
};

const VERDICT_WORD: Record<VerdictKind, string> = {
  got_through: "Got through",
  unconfirmed: "Not confirmed",
  stuck: "Got stuck",
  login_wall: "Stopped at a login",
  bot_check: "Blocked by a bot check",
  our_failure: "Failed on our side",
};

const LEVEL_TONE = {
  clear: "bg-success-soft text-success",
  partly: "bg-warning-soft text-warning",
  unclear: "bg-danger-soft text-danger",
};

function Answer({ question, answer, tone, children, basis, showBasis }: {
  question: string;
  answer: string;
  tone: string;
  children?: ReactNode;
  basis: Basis;
  showBasis: boolean;
}) {
  return (
    <div className="space-y-2 rounded-xl border border-line bg-surface p-4">
      <h3 className="text-sm font-medium text-subtle">{question}</h3>
      <p>
        <span className={`rounded-full px-2.5 py-0.5 text-sm font-semibold ${tone}`}>{answer}</span>
      </p>
      <div className="space-y-1 text-sm text-muted">{children}</div>
      <BasisBadge basis={basis} show={showBasis} />
    </div>
  );
}

// Will they understand it? Can they get value? What to fix first? Answered from the first impression,
// the verdict and the top finding.
export function ThreeAnswers({ run, showBasis }: { run: Run; showBasis: boolean }) {
  const understood = understanding(run.first_impression);
  const verdict = run.verdict;
  const first = fixFirst(run.findings, verdict);
  return (
    <section aria-labelledby="three-answers" className="space-y-3">
      <h2 id="three-answers" className="text-xl font-semibold tracking-tight">
        The short answer
      </h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <Answer
          question="Will a new user understand it?"
          answer={understood ? understood.label : "Not assessed"}
          tone={understood ? LEVEL_TONE[understood.level] : "bg-background text-muted"}
          basis="observed"
          showBasis={showBasis}
        >
          {understood ? (
            understood.reasons.length > 0 ? (
              <ul className="list-disc space-y-1 pl-4">
                {understood.reasons.slice(0, 3).map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
            ) : (
              <p>What it does, who it is for and the main action were all clear on the landing page.</p>
            )
          ) : (
            <p>The landing page could not be reviewed.</p>
          )}
        </Answer>

        <Answer
          question="Can they get value from it?"
          answer={verdict ? VERDICT_WORD[verdict.kind] : "Not assessed"}
          tone={
            verdict
              ? verdict.kind === "got_through"
                ? LEVEL_TONE.clear
                : verdict.kind === "stuck"
                  ? LEVEL_TONE.unclear
                  : LEVEL_TONE.partly
              : "bg-background text-muted"
          }
          basis={verdict?.basis ?? "observed"}
          showBasis={showBasis}
        >
          <p>{verdict ? verdict.headline : "This run has no verdict."}</p>
        </Answer>

        <Answer
          question="What should you fix first?"
          answer={
            first.state === "finding"
              ? first.finding.title
              : first.state === "none"
                ? "Nothing stood out"
                : first.state === "not_about_site"
                  ? "Nothing, from this visit"
                  : "Not available"
          }
          tone="bg-background text-foreground"
          basis={first.state === "finding" ? "recommendation" : "observed"}
          showBasis={showBasis}
        >
          {first.state === "finding" && (
            <p>
              Ranked first of the findings below.{" "}
              <a href="#findings" className="text-accent hover:underline">
                See the finding
              </a>
              .
            </p>
          )}
          {first.state === "none" && <p>Nothing in this visit stood out as a problem with your site.</p>}
          {first.state === "not_about_site" && (
            <p>This visit says nothing about your site, so there is nothing to fix from it.</p>
          )}
        </Answer>
      </div>
      {showBasis && (
        <p className="text-xs text-subtle">
          Each answer is labelled by what it rests on. <strong>Observed</strong>: from the record of the visit.{" "}
          <strong>Verified</strong>: confirmed by an independent check. <strong>Recommendation</strong>: our
          suggestion, not a measured result.
        </p>
      )}
    </section>
  );
}

// The verdict: one headline, what it rests on, where it happened, and for a login wall the ways in.
export function VerdictCard({ verdict, run, showBasis, showSuccess }: {
  verdict: Verdict;
  run: Run;
  showBasis: boolean;
  showSuccess: boolean;
}) {
  return (
    <div className={`space-y-3 rounded-xl border p-5 ${VERDICT_TONE[verdict.kind]}`}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-lg font-semibold">{verdict.headline}</p>
        <BasisBadge basis={verdict.basis} show={showBasis} />
      </div>
      {verdict.evidence_quote && (
        <p className="text-foreground">
          <span className="text-subtle">
            {verdict.kind === "got_through"
              ? "What confirmed it: "
              : verdict.kind === "unconfirmed"
                ? "What the check could not see: "
                : "Evidence: "}
          </span>
          {verdict.evidence_quote}
        </p>
      )}
      {verdict.detail && verdict.kind !== "unconfirmed" && <p className="text-sm text-muted">{verdict.detail}</p>}
      {(verdict.where_step !== null || verdict.where_url) && (
        <p className="text-sm text-muted">
          {verdict.where_step !== null && (
            <a href={`#step-${verdict.where_step}`} className="text-accent hover:underline">
              Step {verdict.where_step}
            </a>
          )}
          {verdict.where_step !== null && verdict.where_url ? " on " : ""}
          {verdict.where_url ? shortUrl(verdict.where_url) : ""}
        </p>
      )}
      {verdict.kind === "login_wall" && verdict.ways_in && (
        <div className="space-y-2 text-sm">
          <p className="font-medium">Three ways in</p>
          <ol className="list-decimal space-y-1 pl-5">
            {verdict.ways_in.map((way, index) => (
              <li key={index}>{way}</li>
            ))}
          </ol>
        </div>
      )}
      {showSuccess && (
        <p className="text-sm text-muted">
          {run.success_condition ? (
            <>
              <span className="text-subtle">Success condition you gave: </span>
              {run.success_condition}
            </>
          ) : (
            "The goal was checked without a stated success condition."
          )}
        </p>
      )}
      {run.reason && run.outcome !== "achieved" && (
        <p className="text-sm text-muted">
          <span className="text-subtle">The visitor&apos;s own report: </span>
          {run.reason}
        </p>
      )}
    </div>
  );
}

function fmtDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  return total < 60 ? `${total} s` : `${Math.floor(total / 60)} min ${total % 60} s`;
}

// "How this report was made", collapsed. Everything here is counted from the run, none of it is written
// by a model. The trace id is plain text.
export function RunFactsPanel({ run, steps }: { run: Run; steps: Step[] }) {
  const facts: RunFacts | null = run.run_facts;
  const cost = facts ? facts.cost_usd : Number(run.cost_usd ?? 0);
  const rows: [string, ReactNode][] = [];
  rows.push(["Steps taken", String(facts?.steps_taken ?? steps.length)]);
  if (facts) {
    rows.push([
      "Actions that needed recovery",
      facts.recoveries.length === 0
        ? "None"
        : facts.recoveries.map((r) => `step ${r.step}, rung ${r.rung} (${r.how})`).join("; "),
    ]);
    rows.push([
      "Our own issues",
      facts.own_issues.length === 0
        ? "None"
        : `${facts.own_issues.length}: ` +
          facts.own_issues.map((i) => (i.step !== null ? `step ${i.step}` : "a step")).join(", ") +
          " (our browser tool had no effect; not the site's fault)",
    ]);
    rows.push(["Page reloads", String(facts.page_reloads)]);
    rows.push([
      "Page errors recorded",
      facts.page_error_count === 0 ? "None" : (
        <ul className="list-disc space-y-1 pl-4">
          {facts.page_errors.map((error, index) => (
            <li key={index} className="break-all">
              {error}
            </li>
          ))}
          {facts.page_error_count > facts.page_errors.length && (
            <li>and {facts.page_error_count - facts.page_errors.length} more</li>
          )}
        </ul>
      ),
    ]);
    rows.push([
      "Independent check",
      facts.verifier ? `${facts.verifier.verdict}: ${facts.verifier.quote}` : "Not run (the visitor did not claim to reach the goal)",
    ]);
    rows.push([
      "Success condition",
      facts.success_condition ?? "None given: the goal was checked as worded",
    ]);
  }
  rows.push(["Cost", `$${cost.toFixed(cost < 0.1 ? 4 : 2)}`]);
  rows.push([
    "Duration",
    facts ? fmtDuration(facts.duration_seconds) : run.started_at && run.finished_at
      ? fmtDuration((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000)
      : "—",
  ]);
  if (facts?.agent_version) rows.push(["Agent version", facts.agent_version]);
  if (facts?.worker_id) rows.push(["Worker", facts.worker_id]);
  if (facts?.trace_id) rows.push(["neatlogs trace ID", <code key="t" className="break-all">{facts.trace_id}</code>]);

  return (
    <details className="rounded-xl border border-line bg-surface p-4">
      <summary className="cursor-pointer font-medium">How this report was made</summary>
      <dl className="mt-4 space-y-3 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="grid gap-1 sm:grid-cols-[14rem_1fr]">
            <dt className="text-subtle">{label}</dt>
            <dd className="break-words">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-subtle">
        The visit is a simulated user, so treat findings as leads to check. Recommendations are our suggestions and
        promise no outcome.
      </p>
    </details>
  );
}

// A recommendation as the page shows it: our wording, labelled, never promising a result.
export function Recommendation({ text, showBasis }: { text: string; showBasis: boolean }) {
  const safe = withoutPromises(text);
  if (!safe) return null;
  return (
    <span>
      {safe} <BasisBadge basis="recommendation" show={showBasis} />
    </span>
  );
}

