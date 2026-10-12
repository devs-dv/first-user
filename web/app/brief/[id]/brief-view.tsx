"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { hiddenTextNote, isBrief, isFailure, safeHref, sortClaims, testJourneyHref } from "@/lib/brief-logic";
import type { Brief, BriefClaim, BriefRun, ClaimStatus, SuggestedJourney } from "@/lib/brief-types";
import { grid } from "@/lib/css";
import { founderBriefEnabled } from "@/lib/founder-flag";
import { runForJourney, type BriefTestRun } from "@/lib/journey-progress";
import { siteName } from "@/lib/report-view";
import { useBriefRuns } from "@/lib/use-brief-runs";

import { RunStatusChip } from "../../run-status-chip";

import { FounderView } from "./founder-view";
import { HiddenTextNotice } from "./hidden-text-notice";
import { SourceLink } from "./source-link";

const POLL_MS = 2000;

type State = { kind: "loading" } | { kind: "not_found" } | { kind: "ready"; run: BriefRun };

export function BriefView({ id }: { id: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [connectionTrouble, setConnectionTrouble] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const response = await fetch(`/api/briefs/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (cancelled) return;
        if (response.status === 404) {
          setState({ kind: "not_found" });
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const { run } = (await response.json()) as { run: BriefRun };
        if (cancelled) return;
        setState({ kind: "ready", run });
        setConnectionTrouble(false);
        if (run.status === "done" || run.status === "failed") return;
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
      <main className="fu-page gap-4">
        <p role="status" className="m-0 font-code text-[13px] text-ink3">
          Loading the brief…
        </p>
        {connectionTrouble && <ConnectionNotice />}
      </main>
    );
  }
  if (state.kind === "not_found") {
    return (
      <main className="fu-page gap-5">
        <span className="fu-eyebrow">Understand</span>
        <h1 className="fu-display text-pagetitle">We couldn&apos;t find that brief</h1>
        <p className="m-0 text-[17px] text-ink2">The link may be mistyped, or the brief may no longer exist.</p>
        <Link href="/?mode=understand#fu-form" className="fu-btn fu-btn-md self-start">
          Understand a website →
        </Link>
      </main>
    );
  }

  const { run } = state;
  const ready = isBrief(run.brief) && run.status === "done";
  return (
    <main className="fu-page" style={{ gap: "clamp(36px,5cqi,56px)" }}>
      {ready ? (
        <Ready id={run.id} run={run} brief={run.brief as Brief} />
      ) : (
        <>
          <BriefHeader run={run} />
          {connectionTrouble && <ConnectionNotice />}
          {run.status === "queued" || run.status === "running" ? (
            <InProgress queued={run.status === "queued"} />
          ) : (
            <Failed message={isFailure(run.brief) ? run.brief.message : null} />
          )}
        </>
      )}
    </main>
  );
}

function BriefHeader({ run, tabs }: { run: BriefRun; tabs?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-[18px]">
      <div className="flex min-w-0 flex-col gap-2.5">
        <span className="fu-eyebrow">
          Understand ·{" "}
          <a href={safeHref(run.url) ?? undefined} target="_blank" rel="noopener noreferrer nofollow" className="fu-link">
            {siteName(run.url)}
          </a>
        </span>
        <h1 className="fu-display text-pagetitle" style={{ overflowWrap: "anywhere" }}>
          {siteName(run.url)}
        </h1>
      </div>
      {tabs}
    </div>
  );
}

function ConnectionNotice() {
  return (
    <p role="status" className="fu-notice m-0">
      We lost the connection for a moment. Still trying.
    </p>
  );
}

function InProgress({ queued }: { queued: boolean }) {
  return (
    <section role="status" className="fu-card-sm flex flex-col gap-3 p-6">
      <span className="flex items-center gap-2 font-code text-[12px] font-medium uppercase tracking-[.06em] text-ink3">
        <span aria-hidden className="size-2 rounded-full" style={{ background: queued ? "var(--ink4)" : "var(--pass)", animation: "fuBlink 1.6s ease-in-out infinite" }} />
        {queued ? "Waiting for a free worker" : "Reading the site now"}
      </span>
      <p className="m-0 text-[16px] leading-normal text-ink2">
        We read the homepage and a few more public pages, then write the brief. This usually takes under a minute. This page
        updates by itself, and you can come back to this link later.
      </p>
    </section>
  );
}

function Failed({ message }: { message: string | null }) {
  return (
    <section role="alert" className="flex flex-col gap-3 rounded-cardsm border-[1.5px] border-dashed border-ink p-6">
      <h2 className="m-0 text-[19px] font-semibold">We couldn&apos;t write a brief for this site</h2>
      <p className="m-0 text-[16px] leading-normal text-ink2">{message ?? "Something went wrong on our side. Please try again in a minute."}</p>
      <Link href="/?mode=understand#fu-form" className="fu-btn fu-btn-md self-start">
        Try another website →
      </Link>
    </section>
  );
}

function Ready({ id, run, brief }: { id: string; run: BriefRun; brief: Brief }) {
  const [tab, setTab] = useState<"product" | "founder">("product");
  // The founder brief is behind NEXT_PUBLIC_FOUNDER_BRIEF; without it this page is the product brief alone.
  const founder = founderBriefEnabled();
  const tabs = founder ? (
    <div role="tablist" aria-label="Which brief" className="flex gap-1 rounded-pill border-[1.5px] border-ink bg-s1 p-1">
      {(
        [
          ["product", "Product brief"],
          ["founder", "Founder brief"],
        ] as const
      ).map(([value, label]) => {
        const on = tab === value;
        return (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => setTab(value)}
            className="h-10 cursor-pointer whitespace-nowrap rounded-pill border-none px-4 text-[14px] font-semibold"
            style={{ background: on ? "var(--ink)" : "transparent", color: on ? "var(--bg)" : "var(--ink)" }}
          >
            {label}
          </button>
        );
      })}
    </div>
  ) : null;
  return (
    <>
      <BriefHeader run={run} tabs={tabs} />
      {founder && tab === "founder" ? <FounderView briefId={id} /> : <ProductBrief id={id} brief={brief} />}
    </>
  );
}

function ProductBrief({ id, brief }: { id: string; brief: Brief }) {
  const hidden = hiddenTextNote(brief);
  const overview: [string, string][] = [
    ["What it does", brief.what_it_does],
    ["Who it's for", brief.who_its_for],
    ["How it works", brief.how_it_works],
    ["Primary value", brief.primary_value],
  ];
  return (
    <div className="flex flex-col" style={{ gap: "clamp(36px,5cqi,56px)" }}>
      {hidden && <HiddenTextNotice note={hidden} />}
      <Journeys id={id} siteUrl={brief.url} journeys={brief.suggested_journeys ?? []} />

      <section aria-label="Summary" className="fu-grid border-t-[1.5px] border-ink pt-7" style={grid("300px", "clamp(20px,3cqi,40px)")}>
        <p className="m-0 text-[clamp(22px,2.6cqi,30px)] font-medium leading-[1.3] fu-pretty">{brief.one_liner}</p>
        <dl className="m-0 flex flex-col">
          {overview.map(([label, value]) => {
            const unknown = !value || value === "unknown";
            return (
              <div key={label} className="flex flex-col gap-1 border-b border-line py-3">
                <dt className="font-code text-[12px] font-medium uppercase tracking-[.04em] text-ink3">{label}</dt>
                <dd className={`m-0 text-[16px] leading-normal ${unknown ? "text-ink3" : ""}`}>
                  {unknown ? "Unknown: the site doesn't say." : value}
                </dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section aria-label="Pricing and business model" className="fu-grid" style={grid("300px")}>
        <Pricing pricing={brief.pricing} />
        <BusinessModel model={brief.business_model} />
      </section>

      <Claims claims={brief.claims ?? []} />

      <section aria-label="Unknowns and pages read" className="fu-grid" style={grid("300px")}>
        <div className="flex flex-col gap-2.5 rounded-cardsm border-[1.5px] border-dashed border-ink3 p-[22px]">
          <h2 className="m-0 text-[19px] font-semibold">What we couldn&apos;t confirm</h2>
          {(brief.unknowns ?? []).length === 0 ? (
            <p className="m-0 text-[15px] text-ink2">Nothing listed.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {brief.unknowns.map((item, index) => (
                <li key={index} className="text-[15px] leading-normal text-ink2">
                  · {item}
                </li>
              ))}
            </ul>
          )}
        </div>
        <PagesRead brief={brief} />
      </section>

      <p className="m-0 text-[14px] leading-normal text-ink3">
        This brief is written from the public pages listed above and nothing else. Marketing claims are goals to test, not proof
        that the product does them.
      </p>
    </div>
  );
}

// The main call to action: each journey is editable in place, and "Test this journey" opens the test
// form with the URL, the goal and the success condition as they are now.
function Journeys({ id, siteUrl, journeys }: { id: string; siteUrl: string; journeys: SuggestedJourney[] }) {
  // Tests already started from this brief: each journey card shows how its newest one went.
  const runs = useBriefRuns(journeys.length > 0 ? id : null);
  return (
    <section aria-labelledby="journeys-title" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <h2 id="journeys-title" className="fu-display fu-display-wide text-card" style={{ lineHeight: 1 }}>
          Suggested journeys
        </h2>
        <span className="text-[15px] text-ink2">
          Taken from the site&apos;s own calls to action and claims. Pick one, edit it if you like, and test it.
        </span>
      </div>
      {journeys.length === 0 ? (
        <p className="m-0 rounded-cardsm border-[1.5px] border-dashed border-ink3 p-5 text-[15px] text-ink2">
          The pages we read gave nothing specific enough to suggest a goal. You can still{" "}
          <Link href={testJourneyHref(id, siteUrl, "", "")} className="fu-link font-semibold">
            write your own goal
          </Link>
          .
        </p>
      ) : (
        <ol className="fu-grid m-0 list-none p-0" style={grid("280px")}>
          {journeys.map((journey, index) => (
            <Journey key={`${index}-${journey.goal}`} index={index} id={id} siteUrl={siteUrl} journey={journey} tested={runForJourney(journey, runs ?? [])} />
          ))}
        </ol>
      )}
    </section>
  );
}

function Journey({ index, id, siteUrl, journey, tested }: {
  index: number;
  id: string;
  siteUrl: string;
  journey: SuggestedJourney;
  tested: BriefTestRun | null;
}) {
  const [goal, setGoal] = useState(journey.goal);
  const [success, setSuccess] = useState(journey.success);
  // Grows with its text where the browser supports it; three rows otherwise.
  const field = "h-auto min-h-[46px] resize-y py-2.5 text-[15px] leading-snug [field-sizing:content]";
  return (
    <li className="fu-card-sm flex flex-col gap-3.5 p-5">
      <span className="flex min-h-6 flex-wrap items-center justify-between gap-2">
        <span className="font-code text-[12px] font-medium text-ink3">{String(index + 1).padStart(2, "0")}</span>
        {tested && (
          <Link
            href={`/run/${tested.id}`}
            className="flex items-center gap-2 text-[13px] font-semibold text-ink no-underline hover:underline"
          >
            <RunStatusChip status={tested.status} verdictKind={tested.verdict_kind} />
            {tested.status === "done" || tested.status === "failed" ? "Report →" : "Watch →"}
          </Link>
        )}
      </span>
      <label className="flex flex-col gap-1.5">
        <span className="fu-eyebrow-sm">Goal</span>
        <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={3} maxLength={500} className={`fu-field ${field} font-semibold`} />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="fu-eyebrow-sm">Success looks like</span>
        <textarea value={success} onChange={(event) => setSuccess(event.target.value)} rows={3} maxLength={300} className={`fu-field ${field}`} />
      </label>
      <div className="fu-quote">
        <span className="text-[13px] text-ink3">{journey.claim_to_test ? "A claim to test, not proof that it works" : "A call to action on the site"}</span>
        <span className="text-[14px] leading-[1.45] text-ink2">&ldquo;{journey.basis_text}&rdquo;</span>
        <SourceLink url={journey.source_url} />
      </div>
      <Link href={testJourneyHref(id, siteUrl, goal, success)} className="fu-btn mt-auto">
        {tested ? "Test it again →" : "Test this journey →"}
      </Link>
    </li>
  );
}

function Pricing({ pricing }: { pricing: Brief["pricing"] }) {
  const published = pricing.status === "published" && pricing.tiers.length > 0;
  const firstSource = pricing.source_urls?.[0] ?? pricing.tiers[0]?.source_url;
  return (
    <div className="fu-card-sm flex flex-col gap-3.5 p-[22px]">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <h2 className="m-0 text-[19px] font-semibold">Pricing</h2>
        {published && firstSource ? (
          <SourceLink url={firstSource} />
        ) : (
          <span className="fu-chip fu-chip-tag bg-s2 text-ink3">{pricing.status === "unclear" ? "Unclear" : "Not published"}</span>
        )}
      </div>
      {published ? (
        <ul className="m-0 flex list-none flex-col p-0">
          {pricing.tiers.map((tier, index) => (
            <li key={`${index}-${tier.name}`} className="flex flex-col gap-1 border-t border-line py-2.5">
              <span className="flex justify-between gap-3">
                <span className="text-[15px] font-semibold">{tier.name}</span>
                <span className="text-right font-code text-[14px] font-medium">{tier.price}</span>
              </span>
              {tier.what_you_get && tier.what_you_get !== "unknown" && (
                <span className="text-[13px] leading-[1.45] text-ink2">{tier.what_you_get}</span>
              )}
              {tier.source_url !== firstSource && <SourceLink url={tier.source_url} />}
            </li>
          ))}
        </ul>
      ) : (
        <p className="m-0 text-[15px] leading-normal text-ink2">
          {pricing.status === "unclear" ? "The pages we read don't make the prices clear." : "Not published on the pages we read."}
        </p>
      )}
      {pricing.note && <p className="m-0 text-[13px] leading-normal text-ink3">{pricing.note}</p>}
      {!published && (pricing.source_urls ?? []).length > 0 && (
        <span className="flex flex-wrap items-center gap-2 text-[13px] text-ink3">
          Where we looked:
          {pricing.source_urls.map((url) => (
            <SourceLink key={url} url={url} />
          ))}
        </span>
      )}
    </div>
  );
}

function BusinessModel({ model }: { model: Brief["business_model"] }) {
  const unknown = !model.model || model.model === "unknown";
  return (
    <div className="fu-card-sm flex flex-col gap-3.5 p-[22px]">
      <div className="flex items-center justify-between gap-2.5">
        <h2 className="m-0 text-[19px] font-semibold">Business model</h2>
        <span className="fu-chip fu-chip-tag border-dashed border-ink bg-amber-soft text-amber-ink">Inferred</span>
      </div>
      <p className={`m-0 text-[17px] font-medium leading-[1.45] ${unknown ? "text-ink3" : ""}`}>
        {unknown ? "Unknown: the pages give no evidence." : model.model}
      </p>
      {model.evidence.map((item, index) => (
        <div key={index} className="fu-quote">
          <span className="text-[14px] text-ink2">&ldquo;{item.quote}&rdquo;</span>
          <SourceLink url={item.source_url} />
        </div>
      ))}
    </div>
  );
}

const STATUS: Record<ClaimStatus, { label: string; bg: string; fg: string }> = {
  confirmed: { label: "Confirmed", bg: "var(--green-soft)", fg: "var(--green-ink)" },
  inferred: { label: "Inferred", bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  unknown: { label: "Unknown", bg: "var(--s2)", fg: "var(--ink3)" },
};

function Claims({ claims }: { claims: BriefClaim[] }) {
  if (claims.length === 0) return null;
  return (
    <section aria-labelledby="claims-title" className="flex flex-col gap-3.5">
      <div className="flex flex-col gap-1">
        <h2 id="claims-title" className="m-0 text-[19px] font-semibold">
          Claims on the site
        </h2>
        <span className="text-[14px] text-ink3">Confirmed means the site says it, in the quoted words. It does not mean we checked it is true.</span>
      </div>
      <ul className="m-0 list-none overflow-hidden rounded-cardsm border-[1.5px] border-ink bg-s1 p-0">
        {sortClaims(claims).map((claim, index) => {
          const status = STATUS[claim.status] ?? STATUS.unknown;
          return (
            <li key={index} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 py-3.5" style={{ borderTop: index ? "1px solid var(--line)" : "none" }}>
              <span className="flex min-w-[min(100%,220px)] flex-1 flex-col gap-1">
                <span className="text-[16px] leading-[1.45]">{claim.claim}</span>
                {claim.quote && <span className="text-[14px] leading-[1.45] text-ink3">&ldquo;{claim.quote}&rdquo;</span>}
              </span>
              <span className="flex items-center gap-2.5">
                <span className="fu-chip fu-chip-word" style={{ background: status.bg, color: status.fg }}>
                  {status.label}
                </span>
                <SourceLink url={claim.source_url} />
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function PagesRead({ brief }: { brief: Brief }) {
  return (
    <div className="flex flex-col gap-2.5 rounded-cardsm border-[1.5px] border-line bg-s1 p-[22px]">
      <h2 className="m-0 text-[19px] font-semibold">Pages read</h2>
      <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
        {brief.pages.map((page) => {
          const href = safeHref(page.url);
          const label = (() => {
            try {
              return new URL(page.url).pathname;
            } catch {
              return page.url;
            }
          })();
          return (
            <li key={page.url}>
              <a
                href={href ?? undefined}
                target="_blank"
                rel="noopener noreferrer nofollow"
                title={`${page.kind}${page.method === "browser" ? " (needed a browser)" : ""}`}
                className="flex h-[30px] items-center whitespace-nowrap rounded-r8 border border-line bg-bg px-2.5 font-code text-[13px] font-medium hover:border-ink"
              >
                {label}
              </a>
            </li>
          );
        })}
      </ul>
      {brief.skipped.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="fu-eyebrow-sm">Not read</span>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[13px] text-ink3">
            {brief.skipped.map((item, index) => (
              <li key={index}>
                <SourceLink url={item.url} /> · {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
