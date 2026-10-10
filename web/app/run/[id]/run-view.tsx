"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { Friction, Outcome, Run, RunDetails, Step } from "@/lib/types";

const POLL_MS = 2000;

type State = { kind: "loading" } | { kind: "not_found" } | { kind: "ready"; data: RunDetails };

export function RunView({ id }: { id: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [connectionTrouble, setConnectionTrouble] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (cancelled) return;
        if (response.status === 404) {
          setState({ kind: "not_found" });
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as RunDetails;
        if (cancelled) return;
        setState({ kind: "ready", data });
        setConnectionTrouble(false);
        if (data.run.status === "done" || data.run.status === "failed") return;
      } catch {
        if (cancelled) return;
        setConnectionTrouble(true);
      }
      timer = setTimeout(poll, POLL_MS);
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (state.kind === "loading") {
    return (
      <div className="space-y-4">
        <p className="text-muted">Loading the run…</p>
        {connectionTrouble && <ConnectionNotice />}
      </div>
    );
  }
  if (state.kind === "not_found") return <NotFound />;

  const { run, steps, frictions } = state.data;
  return (
    <div className="space-y-10">
      <RunHeader run={run} />
      {connectionTrouble && <ConnectionNotice />}
      {run.status === "queued" || run.status === "running" ? (
        <InProgress run={run} steps={steps} />
      ) : run.status === "failed" ? (
        <Failed steps={steps} frictions={frictions} />
      ) : (
        <Report run={run} steps={steps} frictions={frictions} />
      )}
    </div>
  );
}

function RunHeader({ run }: { run: Run }) {
  return (
    <section className="space-y-3">
      <p className="text-sm font-medium uppercase tracking-wide text-subtle">First visit to</p>
      <h1 className="break-all text-2xl font-semibold leading-snug tracking-tight sm:text-3xl">
        <a href={run.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:underline">
          {displayUrl(run.url)}
        </a>
      </h1>
      <p className="text-muted">
        <span className="text-subtle">Goal: </span>
        {run.goal}
      </p>
    </section>
  );
}

function InProgress({ run, steps }: { run: Run; steps: Step[] }) {
  const queued = run.status === "queued";
  return (
    <>
      <section role="status" className="rounded-xl border border-line bg-surface p-5">
        <div className="flex items-center gap-3">
          <span aria-hidden className={`size-2.5 rounded-full ${queued ? "bg-subtle" : "bg-accent"}`} />
          <p className="font-medium">{queued ? "Waiting for a free browser" : "Visiting your site now"}</p>
        </div>
        <p className="mt-2 text-sm text-muted">
          {queued
            ? "Your run is in the queue and will start shortly."
            : `${steps.length} ${steps.length === 1 ? "step" : "steps"} so far.`}{" "}
          This page updates by itself, and you can come back to this link later.
        </p>
      </section>
      {steps.length > 0 && <Timeline steps={steps} />}
    </>
  );
}

function Failed({ steps, frictions }: { steps: Step[]; frictions: Friction[] }) {
  return (
    <>
      <section role="alert" className="rounded-xl border border-danger/30 bg-danger-soft p-5">
        <p className="font-medium text-danger">This run didn&apos;t finish</p>
        <p className="mt-2 text-sm">
          Something went wrong on our side, so this tells you nothing about your site.
          {steps.length > 0 && " The steps recorded before it stopped are below."}
        </p>
        <Link href="/" className="mt-4 inline-block text-sm font-medium text-accent hover:underline">
          Start a new run
        </Link>
      </section>
      {frictions.length > 0 && <Frictions frictions={frictions} />}
      {steps.length > 0 && <Timeline steps={steps} />}
    </>
  );
}

const OUTCOMES: Record<Outcome, { label: string; tone: string }> = {
  achieved: { label: "Reached the goal", tone: "border-success/30 bg-success-soft text-success" },
  blocked: { label: "Got blocked", tone: "border-danger/30 bg-danger-soft text-danger" },
  gave_up: { label: "Gave up", tone: "border-warning/30 bg-warning-soft text-warning" },
  max_steps: { label: "Ran out of steps", tone: "border-warning/30 bg-warning-soft text-warning" },
  error: { label: "Didn't finish", tone: "border-danger/30 bg-danger-soft text-danger" },
};

function Report({ run, steps, frictions }: { run: Run; steps: Step[]; frictions: Friction[] }) {
  const outcome = OUTCOMES[run.outcome ?? "error"] ?? OUTCOMES.error;
  return (
    <>
      <section className="space-y-4">
        <div className={`rounded-xl border p-5 ${outcome.tone}`}>
          <p className="text-lg font-semibold">{outcome.label}</p>
          {run.reason && <p className="mt-2 text-foreground">{run.reason}</p>}
        </div>
        <p className="text-sm text-muted">This is a simulated user. Treat findings as leads to check.</p>
        <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <Fact label="Steps" value={String(steps.length)} />
          <Fact label="Time" value={duration(run.started_at, run.finished_at)} />
          <Fact label="Cost" value={formatCost(run.cost_usd)} />
        </dl>
        <CopyLinkButton />
      </section>
      <Frictions frictions={frictions} />
      <Timeline steps={steps} />
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-subtle">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function CopyLinkButton() {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied("copied");
    } catch {
      setCopied("failed");
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={copy}
        className="rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium hover:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        Copy link to this report
      </button>
      <span aria-live="polite" className="text-sm text-muted">
        {copied === "copied" && "Link copied."}
        {copied === "failed" && "Couldn't copy. Copy the address from your browser instead."}
      </span>
    </div>
  );
}

function Frictions({ frictions }: { frictions: Friction[] }) {
  const site = frictions.filter((f) => f.kind === "site");
  const ours = frictions.filter((f) => f.kind === "agent_issue");
  return (
    <section className="space-y-8">
      <div className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">Problems with the site</h2>
        {site.length === 0 ? (
          <p className="text-muted">The visitor didn&apos;t note any problems.</p>
        ) : (
          <ul className="space-y-3">
            {site.map((friction) => (
              <FrictionItem key={friction.id} friction={friction} />
            ))}
          </ul>
        )}
      </div>
      <div className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">Our agent&apos;s own issues</h2>
        <p className="text-sm text-muted">
          Times our browser tool couldn&apos;t operate something. These are likely our fault, not your site&apos;s.
        </p>
        {ours.length === 0 ? (
          <p className="text-muted">None.</p>
        ) : (
          <ul className="space-y-3">
            {ours.map((friction) => (
              <FrictionItem key={friction.id} friction={friction} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

const SEVERITY_TONE = {
  high: "bg-danger-soft text-danger",
  medium: "bg-warning-soft text-warning",
  low: "bg-background text-muted border border-line",
};

function FrictionItem({ friction }: { friction: Friction }) {
  if (friction.kind === "agent_issue") {
    // The worker writes expected as "'<instruction>' changes the page"; show the instruction alone.
    const instruction = friction.expected?.match(/^'(.*)' changes the page$/)?.[1] ?? friction.expected;
    return (
      <li className="space-y-2 rounded-xl border border-line bg-surface p-4">
        {friction.step_idx !== null && (
          <a href={`#step-${friction.step_idx}`} className="text-sm text-accent hover:underline">
            Step {friction.step_idx}
          </a>
        )}
        {instruction && (
          <p>
            <span className="text-subtle">Tried to: </span>
            {instruction}
          </p>
        )}
        <p className="text-muted">Nothing on the page changed after three different attempts.</p>
      </li>
    );
  }
  return (
    <li className="space-y-2 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {friction.severity && (
          <span className={`rounded-full px-2.5 py-0.5 font-medium ${SEVERITY_TONE[friction.severity]}`}>
            {friction.severity}
          </span>
        )}
        {friction.step_idx !== null && (
          <a href={`#step-${friction.step_idx}`} className="text-accent hover:underline">
            Step {friction.step_idx}
          </a>
        )}
      </div>
      {friction.expected && (
        <p>
          <span className="text-subtle">Expected: </span>
          {friction.expected}
        </p>
      )}
      {friction.happened && (
        <p>
          <span className="text-subtle">What happened: </span>
          {friction.happened}
        </p>
      )}
    </li>
  );
}

function Timeline({ steps }: { steps: Step[] }) {
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Step by step</h2>
      <ol className="space-y-4">
        {steps.map((step) => (
          <StepItem key={step.idx} step={step} />
        ))}
      </ol>
    </section>
  );
}

function StepItem({ step }: { step: Step }) {
  const result = describeResult(step);
  return (
    <li id={`step-${step.idx}`} className="scroll-mt-6 space-y-3 rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="font-medium">
          <span className="mr-2 text-subtle tabular-nums">{step.idx}.</span>
          {describeAction(step)}
        </p>
        {step.url && <p className="min-w-0 truncate text-sm text-subtle">{displayUrl(step.url)}</p>}
      </div>
      {step.thought && <p className="border-l-2 border-line pl-3 italic text-muted">{step.thought}</p>}
      {result && <p className={result.tone === "warn" ? "text-warning" : ""}>{result.text}</p>}
      {isHttpUrl(step.screenshot_path) && (
        <a href={step.screenshot_path} target="_blank" rel="noopener noreferrer" className="block">
          {/* Screenshots are stored in Supabase Storage; a plain img avoids configuring remote image hosts. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={step.screenshot_path}
            alt={`The page after step ${step.idx}`}
            loading="lazy"
            className="w-full rounded-lg border border-line"
          />
        </a>
      )}
    </li>
  );
}

function describeAction(step: Step): string {
  const input = step.input ?? {};
  switch (step.tool) {
    case "look":
      return "Looked at the page";
    case "do":
      return `Tried to ${text(input.instruction) || "act on the page"}`;
    case "scroll":
      return `Scrolled ${text(input.direction) || "the page"}`;
    case "go_back":
      return "Went back";
    case "note_friction":
      return "Noted a problem";
    case "finish":
      return "Ended the visit";
    default:
      return step.tool;
  }
}

function describeResult(step: Step): { text: string; tone?: "warn" } | null {
  const result = step.result ?? {};
  const input = step.input ?? {};
  if (result.error) return { text: "The browser tool hit an error on this step.", tone: "warn" };
  switch (step.tool) {
    case "look":
      return result.unchanged
        ? { text: "Nothing had changed since the last look." }
        : { text: tidySummary(text(result.summary)) };
    case "do":
      if (result.success) return { text: RETRY_WORDING[text(result.rung)] ?? "It worked." };
      return {
        text: "Nothing happened. Our browser tool may have failed here, so this is logged as our issue.",
        tone: "warn",
      };
    case "note_friction":
      return { text: `Expected: ${text(input.expected)} What happened: ${text(input.happened)}` };
    case "finish":
      return { text: text(input.reason) };
    default:
      return null;
  }
}

// Which try of the worker's recovery ladder changed the page (see worker/tools.py do()).
const RETRY_WORDING: Record<string, string> = {
  b: "The first try had no effect. It worked on the second try, after our browser tool looked for the element again.",
  c: "The first two tries had no effect. It worked on the third try, with a direct click on the element.",
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

function ConnectionNotice() {
  return (
    <p role="status" className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm text-warning">
      Having trouble reaching the server. Still trying…
    </p>
  );
}

function NotFound() {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">We couldn&apos;t find that run</h1>
      <p className="text-muted">The link may be mistyped or incomplete. Check it, or start a new run.</p>
      <Link href="/" className="inline-block font-medium text-accent hover:underline">
        Start a new run
      </Link>
    </section>
  );
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function isHttpUrl(value: string | null): value is string {
  return !!value && /^https?:\/\//i.test(value);
}

function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${parsed.host}${path}${parsed.search}`;
  } catch {
    return url;
  }
}

function duration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const seconds = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

function formatCost(cost: number | string | null): string {
  if (cost === null || cost === "") return "—";
  const value = Number(cost);
  return Number.isFinite(value) ? `$${value.toFixed(value < 0.1 ? 4 : 2)}` : "—";
}
