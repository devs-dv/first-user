"use client";

// Check again: the band that re-runs a finished report's journey, and the page of a re-check, which puts
// the old verdict and the new one side by side and labels each old finding. Kept in its own file so the
// report page changes little and the feature can be hidden by flag (lib/report-flags.ts).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { grid } from "@/lib/css";
import { rememberPendingRun } from "@/lib/pending-run";
import { shortUrl } from "@/lib/report-logic";
import { siteName } from "@/lib/report-view";
import type { RetestItem, RetestLabel, RetestResult, RetestVerdictSide, Run, RunLink } from "@/lib/types";

import { VERDICT_LOOK } from "./report-v2";

const LABEL_TEXT: Record<RetestLabel, string> = {
  fixed: "Fixed",
  still_present: "Still present",
  not_reached: "Not reached",
  inconclusive: "Inconclusive",
  new: "New",
};

const LABEL_LOOK: Record<RetestLabel, { bg: string; fg: string }> = {
  fixed: { bg: "var(--green-soft)", fg: "var(--green-ink)" },
  still_present: { bg: "var(--bad-soft)", fg: "var(--bad-ink)" },
  not_reached: { bg: "var(--s2)", fg: "var(--ink3)" },
  inconclusive: { bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  new: { bg: "var(--blue-soft)", fg: "var(--blue-ink)" },
};

const LABEL_MEANING: Record<RetestLabel, string> = {
  fixed: "The step was reached and the original failure was not reproduced under the tested conditions.",
  still_present: "The step was reached and the failure happened again.",
  not_reached: "The state was never reached, so this is unverified. It is not reported as fixed.",
  inconclusive: "The state was reached, but the evidence does not decide it.",
  new: "A problem this check found that was not in the original report.",
};

const PASS_TEXT = { independent: "Decided by the independent visit", guided: "Decided by the guided follow-up" } as const;

// ------------------------------------------------------------------------------------- the band

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
        rememberPendingRun(body.id, { url: run.url, goal: run.goal });
        router.push(`/run/${body.id}`);
        return;
      }
      setError(body?.message ?? "Something went wrong on our side. Please try again in a minute.");
    } catch {
      setError("Couldn't reach the server. Check your connection and try again.");
    }
    setBusy(false);
  }

  return (
    <section
      id="check-again"
      data-reveal=""
      aria-labelledby="check-again-title"
      className="rounded-hero border-[1.5px] border-ink bg-acc text-on-acc"
      style={{ padding: "clamp(24px,3.4cqi,36px)" }}
    >
      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-x-6 gap-y-4">
        <div className="flex min-w-[min(100%,260px)] flex-1 flex-col gap-1.5">
          <h2 id="check-again-title" className="fu-display text-block" style={{ fontStretch: "70%", lineHeight: 0.95 }}>
            Fixed something?
          </h2>
          <p className="m-0 text-[16px] leading-[1.45]">
            Run the same goal again, with the same address, way in and success condition. We compare it with this report,
            finding by finding. The new visit is not told what was found before.
          </p>
        </div>
        <button type="submit" disabled={busy} className="fu-btn fu-btn-dark h-[60px] gap-3 pl-[26px] pr-2 text-[16px]">
          {busy ? "Starting…" : "Check again"}
          <span aria-hidden className="fu-arrow fu-arrow-acc fu-arrow-lg fu-nudge">
            →
          </span>
        </button>
        {needsLogin && (
          <fieldset className="m-0 flex w-full min-w-0 flex-col gap-2 border-none p-0">
            <legend className="mb-2 p-0 text-[14px] font-semibold">Test account</legend>
            <p className="m-0 text-[14px] leading-normal">
              Test logins are never kept after a run, so give one again. Use a throwaway account. Kept only until the check
              starts, never shown to the AI.
            </p>
            <div className="fu-grid" style={grid("220px", "8px")}>
              <input name="testEmail" type="email" autoComplete="off" required aria-label="Test email" placeholder="test@your-app.com" className="fu-field fu-field-mono border-ink-fixed bg-white text-ink-fixed" />
              <input name="testPassword" type="password" autoComplete="new-password" required aria-label="Test password" placeholder="Password" className="fu-field fu-field-mono border-ink-fixed bg-white text-ink-fixed" />
            </div>
          </fieldset>
        )}
        {error && (
          <p role="alert" className="m-0 w-full rounded-field border border-ink-fixed bg-white px-3.5 py-2.5 text-[14px] text-[#9A2214]">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

// ------------------------------------------------------------------------------------- links between reports

// A line under the header: a re-check says which report it re-checks; a report says where its latest
// re-check is. Shown in every state of the run.
export function RetestBanner({ run, latest }: { run: Run; latest?: RunLink | null }) {
  const parts = [];
  if (run.retest_of) {
    parts.push(
      <span key="original">
        This is a check of an earlier report.{" "}
        <Link href={`/run/${run.retest_of}`} className="fu-link font-medium">
          Open the original report
        </Link>
      </span>,
    );
  }
  if (latest) {
    const state = latest.status === "done" || latest.status === "failed" ? "" : " (still running)";
    parts.push(
      <span key="latest">
        Latest check of this report:{" "}
        <Link href={`/run/${latest.id}`} className="fu-link font-medium">
          see what changed{state}
        </Link>
      </span>,
    );
  }
  if (parts.length === 0) return null;
  return (
    <p role="status" className="m-0 flex flex-wrap gap-x-4 gap-y-1 rounded-field border border-line bg-s1 px-4 py-3 text-[14px] text-ink2">
      {parts}
    </p>
  );
}

// ------------------------------------------------------------------------------------- the comparison

function VerdictSide({ title, side, href, linkText }: { title: string; side: RetestVerdictSide; href: string; linkText: string }) {
  const look = side ? VERDICT_LOOK[side.kind] : null;
  return (
    <div
      className="flex flex-col gap-3 rounded-cardsm border-[1.5px] border-ink p-6"
      style={{ background: look?.bg ?? "var(--s1)", color: look?.fg ?? "var(--ink)", borderStyle: look?.border ?? "solid" }}
    >
      <span className="flex flex-wrap items-center justify-between gap-2 font-code text-[12px] font-medium uppercase tracking-[.06em]">
        {title}
        {look && (
          <span className="rounded-pill px-2.5 py-1" style={{ background: look.chipBg, color: look.chipFg }}>
            {look.label}
          </span>
        )}
      </span>
      <span className="fu-display text-[clamp(28px,3.6cqi,44px)]" style={{ lineHeight: 0.92, overflowWrap: "anywhere" }}>
        {side ? side.headline : "No verdict"}
      </span>
      <Link href={href} className="fu-link mt-auto text-[15px]" style={{ color: "inherit" }}>
        {linkText}
      </Link>
    </div>
  );
}

function Item({ item, originalId, first }: { item: RetestItem; originalId: string | null; first: boolean }) {
  const look = LABEL_LOOK[item.label];
  return (
    <li className="fu-grid items-start px-[22px] py-[18px]" style={grid("260px", "10px 20px", { borderTop: first ? "none" : "1px solid var(--line)" })}>
      <div className="flex flex-col gap-1.5">
        <span className="text-[16px] font-semibold leading-[1.4]">{item.title}</span>
        <span className="text-[14px] leading-[1.45] text-ink3">{LABEL_MEANING[item.label]}</span>
        {item.reason && <span className="text-[14px] leading-[1.45] text-ink2">{item.reason}</span>}
        <span className="flex flex-wrap gap-x-4 gap-y-1 text-[14px]">
          {originalId && item.original_step != null && (
            <Link href={`/run/${originalId}#step-${item.original_step}`} className="fu-link">
              Original report, step {item.original_step}
              {item.original_url ? ` (${shortUrl(item.original_url)})` : ""}
            </Link>
          )}
          {item.evidence_step != null && (
            <a href={`#step-${item.evidence_step}`} className="fu-link">
              This report, step {item.evidence_step}
            </a>
          )}
          {item.label === "not_reached" && <span className="text-ink3">No step of this report shows it.</span>}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="flex h-7 items-center whitespace-nowrap rounded-pill border border-ink px-3 text-[13px] font-semibold" style={{ background: look.bg, color: look.fg }}>
          {LABEL_TEXT[item.label]}
        </span>
        {item.pass && (
          <span className="flex h-7 items-center whitespace-nowrap rounded-pill border border-dashed border-ink3 px-2.5 font-code text-[11px] font-medium text-ink2">
            {PASS_TEXT[item.pass]}
          </span>
        )}
      </div>
    </li>
  );
}

// What changed since the original: the verdicts side by side, then every old finding labelled, then the new
// problems. Fixed always says what it means.
export function RetestView({ run, original }: { run: Run; original?: RunLink | null }) {
  const retest: RetestResult | null = run.retest;
  const originalId = run.retest_of ?? original?.id ?? null;
  if (!run.retest_of) return null;
  const header = (
    <div className="flex flex-col gap-2.5">
      <span className="fu-eyebrow">Check again · {siteName(run.url)}</span>
      <h2 className="fu-display text-pagetitle">What changed</h2>
    </div>
  );
  if (!retest || retest.error) {
    return (
      <section className="flex flex-col gap-4">
        {header}
        <p className="m-0 rounded-field border border-line bg-s1 p-4 text-[15px] text-ink2">
          {retest?.error
            ? "The comparison with the original could not be made. The visit itself is reported below."
            : run.status === "done"
              ? "No comparison was made for this run."
              : "The comparison is made when this visit finishes."}
        </p>
      </section>
    );
  }
  const counts = retest.counts ?? {};
  const summary = (["fixed", "still_present", "not_reached", "inconclusive", "new"] as RetestLabel[])
    .filter((label) => (counts[label] ?? 0) > 0)
    .map((label) => `${counts[label]} ${LABEL_TEXT[label].toLowerCase()}`)
    .join(", ");
  const items = [
    ...retest.labels,
    ...retest.new.map((item) => ({ ...item, label: "new" as const, pass: "independent" as const, original_step: null })),
  ];
  return (
    <section aria-labelledby="what-changed" className="flex flex-col gap-[clamp(32px,4cqi,48px)]">
      {header}
      {retest.verdict && (
        <div className="flex flex-col gap-3">
          <div className="fu-grid items-stretch" style={grid("280px", "12px")}>
            <VerdictSide title="Before · first run" side={retest.verdict.before} href={originalId ? `/run/${originalId}` : "#"} linkText="Open the first report" />
            <VerdictSide title="After · check again" side={retest.verdict.after} href="#fu-r-verdict" linkText="See this report below" />
          </div>
          {retest.verdict.summary && <p className="m-0 text-[15px] leading-normal text-ink2">{retest.verdict.summary}</p>}
        </div>
      )}
      <div className="flex flex-col gap-3">
        <h2 id="what-changed" className="fu-display fu-display-wide text-card" style={{ lineHeight: 1 }}>
          Each finding
        </h2>
        {summary && <p className="m-0 text-[15px] text-ink2">{summary}.</p>}
        <p className="m-0 rounded-field border border-ink bg-green-soft px-4 py-3 text-[14px] leading-normal text-green-ink">
          Fixed means not reproduced under the tested conditions, not a guarantee.
        </p>
        {items.length === 0 ? (
          <p className="m-0 text-[15px] text-ink2">The original report had no findings to check.</p>
        ) : (
          <ul className="m-0 list-none overflow-hidden rounded-cardsm border-[1.5px] border-ink bg-s1 p-0">
            {items.map((item, index) => (
              <Item key={index} item={item} originalId={originalId} first={index === 0} />
            ))}
          </ul>
        )}
        <p className="m-0 text-[14px] leading-normal text-ink3">
          <strong>Not reached</strong> means the state was never reached, so the issue is unverified.
          {retest.guided && retest.guided.attempted > 0 && (
            <>
              {" "}
              The guided follow-up tried to follow the original route for {retest.guided.attempted} finding
              {retest.guided.attempted === 1 ? "" : "s"} and followed it for {retest.guided.followed}.
            </>
          )}
        </p>
      </div>
    </section>
  );
}
