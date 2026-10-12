"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { hiddenTextNotice } from "@/lib/hidden-text";
import { parsePendingRun, pendingRunSnapshot } from "@/lib/pending-run";
import { readReportFlags, type ReportFlags } from "@/lib/report-flags";
import { showLoginWallHelp } from "@/lib/report-logic";
import { formatSeconds, runSeconds, shareText, siteName, verdictKindOf } from "@/lib/report-view";
import type { Run, RunDetails, RunLink, Step } from "@/lib/types";

import { SharePanel } from "../../share-panel";

import { CheckAgain, RetestBanner, RetestView } from "./check-again";
import { Findings, Frictions } from "./findings";
import { BriefBacklink, TestAnotherJourney, useFromBrief, type FromBrief } from "./from-brief";
import { LiveRun } from "./live-run";
import { displayUrl, formatCost } from "./report-bits";
import { HowMade } from "./how-made";
import { FirstImpressionPanel, HiddenTextLine, ShortAnswer, VerdictHero, heroTitle } from "./report-v2";
import { StepsStrip } from "./steps-strip";

const POLL_MS = 2000;

// The remembered address and goal never change while the page is open, so nothing needs to subscribe.
const noSubscription = () => () => {};

type State = { kind: "loading" } | { kind: "not_found" } | { kind: "ready"; data: RunDetails };

export function RunView({ id }: { id: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [connectionTrouble, setConnectionTrouble] = useState(false);
  // Which Report v2 sections show. `?report=basic` on the address hides them all for that view.
  // Nothing rendered before the run loads depends on it, so reading the address here is safe.
  const pendingRaw = useSyncExternalStore(
    noSubscription,
    () => pendingRunSnapshot(id),
    () => null,
  );
  const [flags] = useState<ReportFlags>(() => readReportFlags(typeof window === "undefined" ? "" : window.location.search));
  const fromBrief = useFromBrief(state.kind === "ready" ? state.data.run.brief_run_id : null);

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

  // Until the first response, the waiting view shows at once, with the address and goal the form remembered.
  if (state.kind === "loading") {
    return (
      <main className="fu-page" style={{ gap: "var(--block-gap)" }}>
        {connectionTrouble && <ConnectionNotice />}
        <LiveRun run={null} steps={[]} pending={parsePendingRun(pendingRaw)} id={id} />
      </main>
    );
  }
  if (state.kind === "not_found") return <NotFound />;

  const { run, steps, frictions, original, latest_retest: latestRetest } = state.data;
  const running = run.status === "queued" || run.status === "running";
  return (
    <main className="fu-page" style={{ gap: "var(--block-gap)" }}>
      <div className="flex flex-col gap-3.5">
        {fromBrief && <BriefBacklink from={fromBrief} />}
        <ReportHeader run={run} steps={steps} flags={flags} running={running} />
      </div>
      {(connectionTrouble || (flags.checkAgain && (run.retest_of || latestRetest))) && (
        <div className="-mt-6 flex flex-col gap-3">
          {flags.checkAgain && <RetestBanner run={run} latest={latestRetest} />}
          {connectionTrouble && <ConnectionNotice />}
        </div>
      )}
      {running ? (
        <InProgress run={run} steps={steps} flags={flags} original={original} />
      ) : (
        <Report run={run} steps={steps} frictions={frictions} flags={flags} original={original} fromBrief={fromBrief} />
      )}
    </main>
  );
}

function ReportHeader({ run, steps, flags, running }: { run: Run; steps: Step[]; flags: ReportFlags; running: boolean }) {
  const site = siteName(run.url);
  const facts = flags.facts ? run.run_facts : null;
  const meta = running
    ? []
    : [
        `${facts?.steps_taken ?? steps.length} steps`,
        formatSeconds(runSeconds(run)),
        formatCost(facts?.cost_usd ?? run.cost_usd),
        ...(facts?.agent_version ? [`Agent ${facts.agent_version}`] : []),
      ].filter((item) => item !== "—");
  const sections: [string, string][] = running
    ? []
    : [
        ["Verdict", "fu-r-verdict"],
        ...(flags.answers ? ([["Short answer", "fu-r-short"]] as [string, string][]) : []),
        ...(run.findings !== null ? ([["Findings", "fu-r-find"]] as [string, string][]) : []),
        ["Every step", "fu-r-steps"],
        ["How it was made", "fu-r-made"],
      ];
  return (
    <div className="flex flex-col gap-[18px]">
      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <div className="flex min-w-0 items-center gap-3">
          <span aria-hidden className="flex size-11 flex-none items-center justify-center rounded-field border-[1.5px] border-ink bg-page-btn text-[18px] font-bold text-white">
            {site.charAt(0).toUpperCase()}
          </span>
          <div className="flex min-w-0 flex-col gap-[3px]">
            <a href={run.url} target="_blank" rel="noopener noreferrer nofollow" className="truncate text-[17px] font-semibold">
              {displayUrl(run.url)}
            </a>
            <span className="text-[14px] text-ink3 [overflow-wrap:anywhere]">Goal · {run.goal}</span>
            {run.start_url && (
              <span className="text-[13px] text-ink3 [overflow-wrap:anywhere]">
                Start link ·{" "}
                <a href={run.start_url} target="_blank" rel="noopener noreferrer nofollow" className="fu-link">
                  {displayUrl(run.start_url)}
                </a>
              </span>
            )}
          </div>
        </div>
        {meta.length > 0 && (
          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0" aria-label="About this run">
            {meta.map((item) => (
              <li key={item} className="flex h-[30px] items-center whitespace-nowrap rounded-pill border border-line bg-s1 px-[11px] font-code text-[12px] font-medium text-ink2">
                {item}
              </li>
            ))}
          </ul>
        )}
      </div>
      {sections.length > 0 && (
        <nav aria-label="Report sections" className="flex gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:none]">
          {sections.map(([label, anchor], index) => (
            <a
              key={anchor}
              href={`#${anchor}`}
              className="flex h-9 flex-none items-center gap-2 whitespace-nowrap rounded-pill border-[1.5px] border-ink bg-bg px-3.5 text-[14px] font-medium transition-[background,transform] duration-200 hover:-translate-y-0.5 hover:bg-acc-soft hover:text-ink"
            >
              <span className="font-code text-[11px] font-medium text-ink3">0{index + 1}</span>
              {label}
            </a>
          ))}
        </nav>
      )}
    </div>
  );
}

function InProgress({ run, steps, flags, original }: { run: Run; steps: Step[]; flags: ReportFlags; original?: RunLink | null }) {
  return (
    <>
      {flags.checkAgain && run.retest_of && <RetestView run={run} original={original} />}
      <LiveRun run={run} steps={steps} />
      <FirstImpressionBlock run={run} flags={flags} open />
      {steps.length > 0 && <StepsStrip steps={steps} highlight={new Set()} live />}
    </>
  );
}

function Report({ run, steps, frictions, flags, original, fromBrief }: {
  run: Run;
  steps: Step[];
  frictions: RunDetails["frictions"];
  flags: ReportFlags;
  original?: RunLink | null;
  fromBrief: FromBrief | null;
}) {
  const loginHelp = showLoginWallHelp(run, steps);
  const kind = verdictKindOf(run, loginHelp, flags.verdict);
  const title = heroTitle(run, steps, kind, flags);
  const done = run.status === "done";
  // Steps a finding or the verdict points at get a red edge in the strip.
  const highlight = new Set<number>();
  for (const finding of run.findings ?? []) {
    highlight.add(finding.evidence.step);
    for (const seen of finding.also_seen_at ?? []) highlight.add(seen.step);
  }
  if (kind === "stuck" && run.verdict?.where_step != null) highlight.add(run.verdict.where_step);

  return (
    <>
      {flags.checkAgain && run.retest_of && <RetestView run={run} original={original} />}
      <VerdictHero run={run} steps={steps} kind={kind} flags={flags} loginHelp={loginHelp && kind !== "login_wall"} />
      {flags.answers && done && <ShortAnswer run={run} kind={kind} title={title} showBasis={flags.labels} />}
      <FirstImpressionBlock run={run} flags={flags} open={!flags.answers} />
      {done && <Findings run={run} flags={flags} kind={kind} />}
      {frictions.length > 0 && <Frictions frictions={frictions} findings={run.findings} />}
      {fromBrief && <TestAnotherJourney from={fromBrief} />}
      {flags.checkAgain && done && <CheckAgain run={run} />}
      <StepsStrip steps={steps} highlight={highlight} />
      <HowMade run={run} steps={steps} showFacts={flags.facts} />
      {done && <SharePanel title="Share this report" makeText={(link) => shareText(siteName(run.url), link, kind)} />}
    </>
  );
}

// The first impression, with the hidden-text notice as its own line just above it.
function FirstImpressionBlock({ run, flags, open }: { run: Run; flags: ReportFlags; open: boolean }) {
  const notice = hiddenTextNotice(run.hidden_text, run.first_impression);
  if (!notice && !run.first_impression) return null;
  return (
    <div className="flex flex-col gap-3">
      <HiddenTextLine run={run} />
      {run.first_impression && <FirstImpressionPanel review={run.first_impression} flags={flags} open={open} />}
    </div>
  );
}

function ConnectionNotice() {
  return (
    <p role="status" className="fu-notice m-0">
      Having trouble reaching the server. Still trying…
    </p>
  );
}

function NotFound() {
  return (
    <main className="fu-page gap-5">
      <span className="fu-eyebrow">Report</span>
      <h1 className="fu-display text-pagetitle">We couldn&apos;t find that run</h1>
      <p className="m-0 max-w-[40em] text-[17px] leading-normal text-ink2">
        The link may be mistyped or incomplete. Check it, or start a new run.
      </p>
      <Link href="/#fu-form" className="fu-btn fu-btn-md self-start">
        Start a new run →
      </Link>
    </main>
  );
}
