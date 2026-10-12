"use client";

// Check again: the button that re-runs a finished report's journey, and the page of a re-check, which puts
// the old verdict and the new one side by side and labels each old finding. Kept in its own file so the
// report page changes little and the feature can be hidden by flag (lib/report-flags.ts).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { shortUrl } from "@/lib/report-logic";
import type { RetestItem, RetestLabel, RetestResult, RetestVerdictSide, Run, RunLink } from "@/lib/types";

const LABEL_TEXT: Record<RetestLabel, string> = {
  fixed: "Fixed",
  still_present: "Still present",
  not_reached: "Not reached",
  inconclusive: "Inconclusive",
  new: "New",
};

const LABEL_TONE: Record<RetestLabel, string> = {
  fixed: "bg-success-soft text-success",
  still_present: "bg-danger-soft text-danger",
  not_reached: "bg-warning-soft text-warning",
  inconclusive: "bg-background text-muted border border-line",
  new: "bg-danger-soft text-danger",
};

const LABEL_MEANING: Record<RetestLabel, string> = {
  fixed: "The step was reached and the original failure was not reproduced under the tested conditions.",
  still_present: "The step was reached and the failure happened again.",
  not_reached: "The state was never reached, so this is unverified. It is not reported as fixed.",
  inconclusive: "The state was reached, but the evidence does not decide it.",
  new: "A problem this check found that was not in the original report.",
};

const PASS_TEXT = { independent: "Independent visit", guided: "Guided follow-up" } as const;

// ------------------------------------------------------------------------------ the button

export function CheckAgain({ run }: { run: Run }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsLogin = run.has_test_login || run.access_mode === "account";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(run.id)}/retest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          needsLogin
            ? { testEmail: String(form.get("testEmail") ?? ""), testPassword: String(form.get("testPassword") ?? "") }
            : {},
        ),
      });
      const body = (await response.json().catch(() => null)) as { id?: string; message?: string } | null;
      if (response.ok && body?.id) {
        router.push(`/run/${body.id}`);
        return;
      }
      setError(body?.message ?? "Something went wrong on our side. Please try again in a minute.");
    } catch {
      setError("Couldn't reach the server. Check your connection and try again.");
    }
    setBusy(false);
  }

  const inputClass =
    "mt-1 block w-full rounded-lg border border-line bg-surface px-3 py-2 text-base text-foreground " +
    "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30";

  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-5" aria-labelledby="check-again">
      <h2 id="check-again" className="text-xl font-semibold tracking-tight">
        Check again
      </h2>
      <p className="text-sm text-muted">
        Fixed something? Run the same journey again, with the same address, goal, way in and success condition, and see
        what changed. The new visit is not told what was found before.
      </p>
      <form onSubmit={onSubmit} className="space-y-3">
        {needsLogin && (
          <fieldset className="space-y-3 rounded-lg border border-line p-3">
            <legend className="px-1 text-sm font-medium">Test account</legend>
            <p className="text-sm text-muted">
              Test logins are never kept after a run, so give one again. Use a throwaway account. Kept only until the
              check starts, never shown to the AI.
            </p>
            <div>
              <label htmlFor="retestEmail" className="text-sm font-medium">
                Test email
              </label>
              <input id="retestEmail" name="testEmail" type="email" autoComplete="off" required className={inputClass} />
            </div>
            <div>
              <label htmlFor="retestPassword" className="text-sm font-medium">
                Test password
              </label>
              <input
                id="retestPassword"
                name="testPassword"
                type="password"
                autoComplete="new-password"
                required
                className={inputClass}
              />
            </div>
          </fieldset>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-accent px-5 py-2.5 font-medium text-white hover:bg-accent-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-60 dark:text-background"
        >
          {busy ? "Starting…" : "Check again"}
        </button>
      </form>
    </section>
  );
}

// ------------------------------------------------------------------------------ links between reports

// A line under the header: a re-check says which report it re-checks; a report says where its latest
// re-check is. Shown in every state of the run.
export function RetestBanner({ run, latest }: { run: Run; latest?: RunLink | null }) {
  const parts = [];
  if (run.retest_of) {
    parts.push(
      <span key="original">
        This is a check of an earlier report.{" "}
        <Link href={`/run/${run.retest_of}`} className="text-accent hover:underline">
          Open the original report
        </Link>
        .
      </span>,
    );
  }
  if (latest) {
    const state = latest.status === "done" || latest.status === "failed" ? "" : " (still running)";
    parts.push(
      <span key="latest">
        Latest check of this report:{" "}
        <Link href={`/run/${latest.id}`} className="text-accent hover:underline">
          see what changed{state}
        </Link>
        .
      </span>,
    );
  }
  if (parts.length === 0) return null;
  return (
    <p role="status" className="space-x-3 rounded-lg border border-line bg-surface p-3 text-sm text-muted">
      {parts}
    </p>
  );
}

// ------------------------------------------------------------------------------ the comparison

function VerdictSide({ title, side, href }: { title: string; side: RetestVerdictSide; href: string }) {
  return (
    <div className="space-y-1 rounded-xl border border-line bg-surface p-4">
      <p className="text-sm text-subtle">{title}</p>
      <p className="font-medium">{side ? side.headline : "No verdict"}</p>
      <p className="text-sm">
        <Link href={href} className="text-accent hover:underline">
          {title === "Before" ? "Original report" : "This report"}
        </Link>
      </p>
    </div>
  );
}

function Item({ item, originalId, thisId }: { item: RetestItem; originalId: string | null; thisId: string }) {
  return (
    <li className="space-y-2 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`rounded-full px-2.5 py-0.5 font-medium ${LABEL_TONE[item.label]}`}>
          {LABEL_TEXT[item.label]}
        </span>
        {item.pass && (
          <span className="rounded-full border border-line px-2.5 py-0.5 text-muted">{PASS_TEXT[item.pass]}</span>
        )}
        <span className="rounded-full border border-line px-2.5 py-0.5 text-muted">Observed in the run</span>
      </div>
      <p className="font-medium">{item.title}</p>
      <p className="text-sm text-muted">{LABEL_MEANING[item.label]}</p>
      {item.reason && <p className="text-sm text-muted">{item.reason}</p>}
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {originalId && item.original_step != null && (
          <Link href={`/run/${originalId}#step-${item.original_step}`} className="text-accent hover:underline">
            Original report, step {item.original_step}
            {item.original_url ? ` (${shortUrl(item.original_url)})` : ""}
          </Link>
        )}
        {item.evidence_step != null && (
          <Link href={`/run/${thisId}#step-${item.evidence_step}`} className="text-accent hover:underline">
            This report, step {item.evidence_step}
          </Link>
        )}
        {item.label === "not_reached" && <span className="text-muted">No step of this report shows it.</span>}
      </p>
    </li>
  );
}

// What changed since the original: the verdicts side by side, then every old finding labelled, then the new
// problems. Fixed always says what it means.
export function RetestComparison({ run, original }: { run: Run; original?: RunLink | null }) {
  const retest: RetestResult | null = run.retest;
  const originalId = run.retest_of ?? original?.id ?? null;
  if (!run.retest_of) return null;
  if (!retest || retest.error) {
    return (
      <section className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
        {retest?.error
          ? "The comparison with the original could not be made. The visit itself is reported below."
          : "No comparison was made for this run."}
      </section>
    );
  }
  const counts = retest.counts ?? {};
  const summary = (["fixed", "still_present", "not_reached", "inconclusive", "new"] as RetestLabel[])
    .filter((label) => (counts[label] ?? 0) > 0)
    .map((label) => `${counts[label]} ${LABEL_TEXT[label].toLowerCase()}`)
    .join(", ");
  return (
    <section className="space-y-4" aria-labelledby="what-changed">
      <div>
        <h2 id="what-changed" className="text-xl font-semibold tracking-tight">
          What changed since the original
        </h2>
        {summary && <p className="mt-1 text-sm text-muted">{summary}.</p>}
      </div>
      {retest.verdict && (
        <div className="space-y-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <VerdictSide title="Before" side={retest.verdict.before} href={originalId ? `/run/${originalId}` : "#"} />
            <VerdictSide title="After" side={retest.verdict.after} href={`/run/${run.id}`} />
          </div>
          <p className="text-sm text-muted">{retest.verdict.summary}</p>
        </div>
      )}
      <ul className="space-y-3">
        {retest.labels.map((item, index) => (
          <Item key={`old-${index}`} item={item} originalId={originalId} thisId={run.id} />
        ))}
        {retest.new.map((item, index) => (
          <Item
            key={`new-${index}`}
            item={{ ...item, label: "new", pass: "independent", original_step: null }}
            originalId={originalId}
            thisId={run.id}
          />
        ))}
      </ul>
      {retest.labels.length === 0 && retest.new.length === 0 && (
        <p className="text-sm text-muted">The original report had no findings to check.</p>
      )}
      <p className="text-sm text-muted">
        <strong>Fixed</strong> means not reproduced under the tested conditions. It is not a guarantee.{" "}
        <strong>Not reached</strong> means the state was never reached, so the issue is unverified.
        {retest.guided && retest.guided.attempted > 0 && (
          <>
            {" "}
            The guided follow-up tried to follow the original route for {retest.guided.attempted} finding
            {retest.guided.attempted === 1 ? "" : "s"} and followed it for {retest.guided.followed}.
          </>
        )}
      </p>
    </section>
  );
}
