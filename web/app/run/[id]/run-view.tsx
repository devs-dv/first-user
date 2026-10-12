"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type {
  Clarity,
  Entry,
  FirstImpression,
  Finding,
  Friction,
  LoginDiagnosis,
  Outcome,
  Run,
  RunDetails,
  Step,
} from "@/lib/types";
import { readReportFlags, type ReportFlags } from "@/lib/report-flags";
import { frictionsNotInFindings, showLoginWallHelp } from "@/lib/report-logic";

import { BasisBadge, Recommendation, RunFactsPanel, ThreeAnswers, VerdictCard } from "./report-v2";

const POLL_MS = 2000;

type State = { kind: "loading" } | { kind: "not_found" } | { kind: "ready"; data: RunDetails };

export function RunView({ id }: { id: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [connectionTrouble, setConnectionTrouble] = useState(false);
  // Which Report v2 sections show. `?report=basic` on the address hides them all for that view.
  // Nothing rendered before the run loads depends on it, so reading the address here is safe.
  const [flags] = useState<ReportFlags>(() =>
    readReportFlags(typeof window === "undefined" ? "" : window.location.search),
  );

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
        <Failed run={run} steps={steps} frictions={frictions} />
      ) : (
        <Report run={run} steps={steps} frictions={frictions} flags={flags} />
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
      {run.start_url && (
        <p className="break-all text-muted">
          <span className="text-subtle">Start link: </span>
          <a href={run.start_url} target="_blank" rel="noopener noreferrer nofollow" className="hover:underline">
            {displayUrl(run.start_url)}
          </a>
        </p>
      )}
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
      {run.first_impression && <FirstImpressionCard review={run.first_impression} />}
      {steps.length > 0 && <Timeline steps={steps} />}
    </>
  );
}

function Failed({ run, steps, frictions }: { run: Run; steps: Step[]; frictions: Friction[] }) {
  return (
    <>
      {run.first_impression && <FirstImpressionCard review={run.first_impression} />}
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
  achieved_unconfirmed: {
    label: "Reached the goal, not independently confirmed",
    tone: "border-warning/30 bg-warning-soft text-warning",
  },
  not_achieved: { label: "Did not reach the goal", tone: "border-danger/30 bg-danger-soft text-danger" },
  // Runs from before the three-way check (2026-10-11).
  unverified: { label: "Said it reached the goal, but we could not confirm it", tone: "border-warning/30 bg-warning-soft text-warning" },
  blocked: { label: "Got blocked", tone: "border-danger/30 bg-danger-soft text-danger" },
  gave_up: { label: "Gave up", tone: "border-warning/30 bg-warning-soft text-warning" },
  max_steps: { label: "Ran out of steps", tone: "border-warning/30 bg-warning-soft text-warning" },
  error: { label: "Didn't finish", tone: "border-danger/30 bg-danger-soft text-danger" },
};

function Report({ run, steps, frictions, flags }: {
  run: Run;
  steps: Step[];
  frictions: Friction[];
  flags: ReportFlags;
}) {
  const botCheck = run.entry?.bot_check ?? null;
  const outcome = botCheck
    ? { label: "Blocked by a bot check", tone: "border-warning/30 bg-warning-soft text-warning" }
    : (OUTCOMES[run.outcome ?? "error"] ?? OUTCOMES.error);
  return (
    <>
      {flags.answers && <ThreeAnswers run={run} showBasis={flags.labels} />}
      {run.first_impression && <FirstImpressionCard review={run.first_impression} flags={flags} />}
      <section className="space-y-4">
        {flags.verdict && run.verdict ? (
          <VerdictCard verdict={run.verdict} run={run} showBasis={flags.labels} showSuccess={flags.success} />
        ) : (
          <div className={`rounded-xl border p-5 ${outcome.tone}`}>
            <p className="text-lg font-semibold">{outcome.label}</p>
            {run.reason && <p className="mt-2 text-foreground">{run.reason}</p>}
          </div>
        )}
        <WayIn run={run} />
        {showLoginWallHelp(run, steps) && <LoginWallHelp run={run} />}
        <p className="text-sm text-muted">This is a simulated user. Treat findings as leads to check.</p>
        <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <Fact label="Steps" value={String(steps.length)} />
          <Fact label="Time" value={duration(run.started_at, run.finished_at)} />
          <Fact label="Cost" value={formatCost(run.cost_usd)} />
        </dl>
        <CopyLinkButton />
      </section>
      <Findings findings={run.findings} flags={flags} />
      <Frictions frictions={frictions} findings={run.findings} />
      {flags.facts && <RunFactsPanel run={run} steps={steps} />}
      <Timeline steps={steps} />
    </>
  );
}

const CLARITY: Record<Clarity, { yes: string; tone: string }> = {
  yes: { yes: "Clear", tone: "bg-success-soft text-success" },
  partly: { yes: "Partly clear", tone: "bg-warning-soft text-warning" },
  no: { yes: "Not clear", tone: "bg-danger-soft text-danger" },
};
const OBVIOUS: Record<Clarity, string> = { yes: "Obvious", partly: "Somewhat obvious", no: "Not obvious" };

function ClarityRow({ label, clarity, summary, obvious }: {
  label: string;
  clarity: Clarity | undefined;
  summary: string | undefined;
  obvious?: boolean;
}) {
  const known = clarity && clarity in CLARITY ? clarity : null;
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <dt className="font-medium">{label}</dt>
        {known && (
          <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${CLARITY[known].tone}`}>
            {obvious ? OBVIOUS[known] : CLARITY[known].yes}
          </span>
        )}
      </div>
      {summary && <dd className="text-muted">{summary}</dd>}
    </div>
  );
}

// What a newcomer sees on the landing page without logging in. Shown first, so a run that was
// blocked at a login still gives the builder something useful.
function FirstImpressionCard({ review, flags = readReportFlags("") }: { review: FirstImpression; flags?: ReportFlags }) {
  const hesitations = review.hesitations ?? [];
  const suggestions = review.suggestions ?? [];
  return (
    <section className="space-y-4" aria-labelledby="first-impression">
      <div>
        <h2 id="first-impression" className="text-xl font-semibold tracking-tight">
          First impression
        </h2>
        <p className="mt-1 text-sm text-muted">
          What a newcomer sees on your landing page, without logging in.{" "}
          <BasisBadge basis="observed" show={flags.labels} />
        </p>
      </div>
      <div className="space-y-5 rounded-xl border border-line bg-surface p-5">
        <dl className="space-y-4">
          <ClarityRow label="What it does" clarity={review.what_it_does?.clear} summary={review.what_it_does?.summary} />
          <ClarityRow label="Who it is for" clarity={review.who_its_for?.clear} summary={review.who_its_for?.summary} />
          <ClarityRow
            label="The main action"
            clarity={review.main_action?.obvious}
            summary={review.main_action?.summary}
            obvious
          />
        </dl>
        {hesitations.length > 0 && (
          <div>
            <h3 className="font-medium">What might make a newcomer hesitate</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
              {hesitations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {suggestions.length > 0 && (
          <div>
            <h3 className="font-medium">Suggestions</h3>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              {suggestions.map((item, index) => (
                <li key={index}>
                  <Recommendation text={item} showBasis={flags.labels} />
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </section>
  );
}

const MODE_LINES: Record<string, string> = {
  public: "You chose no login, so the visitor looked at what is public.",
  link: "You gave a demo or guest link.",
  account: "You gave a test account.",
  signup: "You let the visitor sign up by itself.",
};
const CHALLENGE_WORDS: Record<string, string> = {
  email_verification: "a code or link sent by email",
  captcha: "a CAPTCHA",
  two_factor: "a two-factor code",
};

// What the page said and returned when the visitor submitted a login or sign-up, as a sentence.
function diagnosisLine(d: LoginDiagnosis): string | null {
  const form = d.stage === "sign_in" ? "test login" : "sign-up";
  const step = d.step !== null ? ` (step ${d.step})` : "";
  const status = d.http_statuses.length ? ` The page's own request returned ${d.http_statuses.join(" and ")}.` : "";
  switch (d.result) {
    case "rejected":
      return d.page_message
        ? `The page rejected the ${form}${step}: \u201c${d.page_message}\u201d.${status}`
        : `The page rejected the ${form}${step} and gave no message.${status}`;
    case "needs_verification":
      return `The visit stopped at the ${form}${step}: it needs ${
        CHALLENGE_WORDS[d.challenge ?? ""] ?? "a verification step"
      }, which the visitor cannot do.`;
    case "no_effect":
      return `Submitting the ${form}${step} had no effect: the page did not change and showed no message.`;
    default:
      return null;
  }
}

function wayInLines(run: Run): string[] {
  const entry: Entry | null = run.entry;
  const lines: string[] = [];
  const mode = entry?.access_mode ?? run.access_mode;
  if (mode && MODE_LINES[mode]) lines.push(MODE_LINES[mode]);
  lines.push(
    run.start_url
      ? `Started at the start link you gave (${displayUrl(run.start_url)}).`
      : "Started at your app's address.",
  );
  const diagnosis = entry?.diagnosis ?? null;
  if (entry?.test_login === "used") lines.push("Signed in with your test account.");
  else if (entry?.test_login === "failed" && diagnosis?.stage === "sign_in") {
    lines.push(diagnosisLine(diagnosis) ?? "Tried your test account, but the sign-in did not work.");
  } else if (entry?.test_login === "failed") lines.push("Tried your test account, but the sign-in did not work.");
  else if (entry?.test_login === "provided_not_used" || (!entry && run.has_test_login)) {
    lines.push("A test account was provided, but the visitor did not need it.");
  }
  if (entry?.self_signup === "used") {
    lines.push(
      entry.created_account_email
        ? `Created a test account (${entry.created_account_email}) to get in. You may want to delete it.`
        : "Created a test account to get in.",
    );
  } else if (entry?.self_signup === "blocked_third_party") {
    const options = entry.third_party_options.length ? ` (${entry.third_party_options.join(", ")})` : "";
    lines.push(`Only third-party sign-in was offered${options}. The visitor never uses those.`);
  } else if (entry?.self_signup === "blocked_verification" || entry?.self_signup === "failed") {
    const sentence = diagnosis?.stage === "sign_up" ? diagnosisLine(diagnosis) : null;
    lines.push(
      sentence ??
        (entry.self_signup === "blocked_verification"
          ? "Tried to sign up, but the app needs email verification, which the visitor can't do."
          : "Tried to sign up with a made-up test account, but the form did not accept it."),
    );
  }
  if (entry?.bot_check) {
    lines.push(
      `The site showed a bot check (\u201c${entry.bot_check.phrase}\u201d). The visitor never tries to get past those, so the visit stopped there.`,
    );
  }
  // A login written on the page itself is a way in too, and never "no login".
  if (entry?.page_login === "shown_on_page") {
    lines.push("Typed a login that was written on the page itself, a demo login for visitors. It was not one you gave.");
  } else if (entry?.page_login === "typed") {
    lines.push("Typed a password into a login form. It was not one you gave.");
  }
  const usedAnything =
    !!run.start_url ||
    run.has_test_login ||
    (!!entry && (entry.self_signup !== "not_used" || (entry.page_login ?? "not_used") !== "not_used"));
  if (!usedAnything) lines.push("No login was used: the visitor saw only what is public.");
  return lines;
}

function WayIn({ run }: { run: Run }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 text-sm">
      <p className="font-medium">How the visitor got in</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
        {wayInLines(run).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

// Shown when the run was blocked at a login: the three ways to a deeper visit.
function LoginWallHelp({ run }: { run: Run }) {
  const tried = run.entry;
  return (
    <section className="space-y-3 rounded-xl border border-warning/30 bg-warning-soft p-5" aria-labelledby="deeper">
      <h2 id="deeper" className="text-lg font-semibold">
        Your app was blocked at a login. Ways to go deeper
      </h2>
      <ol className="list-decimal space-y-3 pl-5">
        <li>
          <span className="font-medium">Give a start link.</span> A demo page, guest mode or preview build that is
          already past the login. The visit begins there.
          {run.start_url && " (You gave one this time.)"}
        </li>
        <li>
          <span className="font-medium">Give a throwaway test login.</span> A test email and password for an account
          with no real data. We use it to sign in, keep it only until the run starts, and the AI visitor never sees
          it.
          {tried?.test_login === "failed" && " (The one you gave this time did not work.)"}
        </li>
        <li>
          <span className="font-medium">Let the visitor sign up itself.</span> This works when your signup is an
          email-and-password form that needs no email verification. It never uses Google, GitHub or other
          third-party sign-in.
          {tried?.self_signup === "blocked_verification" && " (Your signup needs email verification.)"}
        </li>
      </ol>
      <Link href="/" className="inline-block text-sm font-medium text-accent hover:underline">
        Start a new run
      </Link>
    </section>
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

function Frictions({ frictions, findings = null }: { frictions: Friction[]; findings?: Finding[] | null }) {
  // What became a finding is shown there, not again here.
  const noted = frictions.filter((f) => f.kind === "site");
  const site = frictionsNotInFindings(noted, findings);
  const inFindings = noted.length - site.length;
  const ours = frictions.filter((f) => f.kind === "agent_issue");
  return (
    <section className="space-y-8">
      <div className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">Problems with the site</h2>
        {site.length === 0 ? (
          <p className="text-muted">
            {inFindings > 0
              ? "Everything the visitor noted is in the findings above."
              : "The visitor didn\u2019t note any problems."}
          </p>
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

const FINDING_KIND: Record<Finding["kind"], string> = {
  site_problem: "Site problem",
  unclear_wording: "Unclear wording",
  hidden_error: "Hidden error",
};

// The report's ranked problems, most likely to stop a new user first, each with a prompt to paste
// into a coding agent. Every one points at a step of the visit.
function Findings({ findings, flags }: { findings: Finding[] | null; flags: ReportFlags }) {
  if (findings === null) return null; // from before the report writer, or it could not be written
  return (
    <section className="space-y-4" aria-labelledby="findings">
      <div>
        <h2 id="findings" className="text-xl font-semibold tracking-tight">
          What to fix first
        </h2>
        <p className="mt-1 text-sm text-muted">
          Ranked by how likely each is to stop a new user. Each one points at a step below.
        </p>
      </div>
      {findings.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-4 text-muted">
          Nothing in this visit stood out as a problem with your site.
        </p>
      ) : (
        <ol className="space-y-4">
          {findings.map((finding, index) => (
            <FindingCard key={index} finding={finding} rank={index + 1} flags={flags} />
          ))}
        </ol>
      )}
    </section>
  );
}

function FindingCard({ finding, rank, flags }: { finding: Finding; rank: number; flags: ReportFlags }) {
  const evidence = finding.evidence;
  return (
    <li className="space-y-4 rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-subtle tabular-nums">{rank}.</span>
          <span className={`rounded-full px-2.5 py-0.5 font-medium ${SEVERITY_TONE[finding.severity]}`}>
            {finding.severity}
          </span>
          <span className="rounded-full border border-line px-2.5 py-0.5 text-muted">{FINDING_KIND[finding.kind]}</span>
          <BasisBadge basis="observed" show={flags.labels && finding.basis !== undefined} />
        </div>
        <h3 className="text-lg font-semibold leading-snug">{finding.title}</h3>
      </div>
      <dl className="space-y-2">
        <div>
          <dt className="text-sm text-subtle">What the visitor expected</dt>
          <dd>{finding.expected}</dd>
        </div>
        <div>
          <dt className="text-sm text-subtle">What happened</dt>
          <dd>{finding.happened}</dd>
        </div>
      </dl>
      <div className="space-y-2 text-sm">
        <p className="font-medium">Evidence</p>
        <ul className="list-disc space-y-1 pl-5 text-muted">
          <li>
            <a href={`#step-${evidence.step}`} className="text-accent hover:underline">
              Step {evidence.step}
            </a>
            {evidence.url && <span> on {displayUrl(evidence.url)}</span>}
          </li>
          {(finding.also_seen_at?.length ?? 0) > 0 && (
            <li>
              Seen again at{" "}
              {finding.also_seen_at!.map((seen, index) => (
                <span key={seen.step}>
                  {index > 0 && ", "}
                  <a href={`#step-${seen.step}`} className="text-accent hover:underline">
                    step {seen.step}
                  </a>
                </span>
              ))}
            </li>
          )}
          {evidence.quote && <li>The page said: &ldquo;{evidence.quote}&rdquo;</li>}
          {evidence.page_errors.map((error, index) => (
            <li key={index}>
              The page reported: <code className="break-all">{error}</code>
            </li>
          ))}
        </ul>
        {isHttpUrl(evidence.screenshot_url) && (
          <a href={evidence.screenshot_url} target="_blank" rel="noopener noreferrer" className="block max-w-md">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={evidence.screenshot_url}
              alt={`The page at step ${evidence.step}`}
              loading="lazy"
              className="w-full rounded-lg border border-line"
            />
          </a>
        )}
      </div>
      <div className="space-y-2 text-sm">
        <p className="font-medium">Steps to reproduce</p>
        <ol className="list-decimal space-y-1 pl-5 text-muted">
          {finding.reproduce.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ol>
      </div>
      {flags.criteria && (finding.acceptance_criteria?.length ?? 0) > 0 && (
        <div className="space-y-2 text-sm">
          <p className="font-medium">
            Acceptance criteria <BasisBadge basis="recommendation" show={flags.labels} />
          </p>
          <ol className="list-decimal space-y-1 pl-5 text-muted">
            {finding.acceptance_criteria!.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ol>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-subtle">The fix prompt below is</span>
        <BasisBadge basis="recommendation" show={flags.labels} />
      </div>
      <FixPrompt prompt={finding.fix_prompt} />
    </li>
  );
}

// The clipboard API needs a secure, focused page; a hidden textarea and execCommand cover the rest.
async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    try {
      const box = document.createElement("textarea");
      box.value = value;
      box.setAttribute("readonly", "");
      box.style.position = "fixed";
      box.style.opacity = "0";
      document.body.appendChild(box);
      box.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(box);
      return ok;
    } catch {
      return false;
    }
  }
}

function FixPrompt({ prompt }: { prompt: string }) {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  async function copy() {
    setCopied((await copyText(prompt)) ? "copied" : "failed");
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={copy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:text-background"
        >
          Copy fix prompt
        </button>
        <span aria-live="polite" className="text-sm text-muted">
          {copied === "copied" && "Copied. Paste it into your coding agent."}
          {copied === "failed" && "Couldn't copy. Select the prompt below and copy it."}
        </span>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted">Show the prompt</summary>
        <pre className="mt-2 whitespace-pre-wrap break-words rounded-lg border border-line bg-background p-3 font-mono text-[13px] leading-relaxed">
          {prompt}
        </pre>
      </details>
    </div>
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
