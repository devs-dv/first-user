"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { isBrief, isFailure, safeHref, sortClaims, testJourneyHref } from "@/lib/brief-logic";
import { founderBriefEnabled } from "@/lib/founder-flag";
import type { Brief, BriefClaim, BriefRun, ClaimStatus, SuggestedJourney } from "@/lib/brief-types";

import { FounderView } from "./founder-view";
import { SourceLink, displayUrl } from "./source-link";

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
      <div className="space-y-4">
        <p className="text-muted">Loading the brief…</p>
        {connectionTrouble && <ConnectionNotice />}
      </div>
    );
  }
  if (state.kind === "not_found") {
    return (
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">We couldn&apos;t find that brief</h1>
        <p className="text-muted">The link may be mistyped, or the brief may no longer exist.</p>
        <Link href="/?mode=understand" className="font-medium text-accent hover:underline">
          Understand a website
        </Link>
      </section>
    );
  }

  const { run } = state;
  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-wide text-subtle">Product brief</p>
        <h1 className="break-all text-2xl font-semibold leading-snug tracking-tight sm:text-3xl">
          <a href={safeHref(run.url) ?? undefined} target="_blank" rel="noopener noreferrer nofollow" className="hover:underline">
            {displayUrl(run.url)}
          </a>
        </h1>
      </header>
      {connectionTrouble && <ConnectionNotice />}
      {run.status === "queued" || run.status === "running" ? (
        <InProgress queued={run.status === "queued"} />
      ) : isBrief(run.brief) && run.status === "done" ? (
        <Ready id={run.id} brief={run.brief} />
      ) : (
        <Failed message={isFailure(run.brief) ? run.brief.message : null} />
      )}
    </div>
  );
}

function ConnectionNotice() {
  return (
    <p role="status" className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
      We lost the connection for a moment. Still trying.
    </p>
  );
}

function InProgress({ queued }: { queued: boolean }) {
  return (
    <section role="status" className="rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center gap-3">
        <span aria-hidden className={`size-2.5 rounded-full ${queued ? "bg-subtle" : "bg-accent"}`} />
        <p className="font-medium">{queued ? "Waiting for a free worker" : "Reading the site now"}</p>
      </div>
      <p className="mt-2 text-sm text-muted">
        We read the homepage and a few more public pages, then write the brief. This usually takes under a minute.
        This page updates by itself, and you can come back to this link later.
      </p>
    </section>
  );
}

function Failed({ message }: { message: string | null }) {
  return (
    <section role="alert" className="rounded-xl border border-danger/30 bg-danger-soft p-5">
      <p className="font-medium text-danger">We couldn&apos;t write a brief for this site</p>
      <p className="mt-2 text-sm">{message ?? "Something went wrong on our side. Please try again in a minute."}</p>
      <Link href="/?mode=understand" className="mt-4 inline-block text-sm font-medium text-accent hover:underline">
        Try another website
      </Link>
    </section>
  );
}

function Ready({ id, brief }: { id: string; brief: Brief }) {
  const [tab, setTab] = useState<"product" | "founder">("product");
  // The founder brief is behind NEXT_PUBLIC_FOUNDER_BRIEF; without it this page is the product brief alone.
  const founder = founderBriefEnabled();
  const tabClass = (active: boolean) =>
    "rounded-lg px-4 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 " +
    (active
      ? "bg-accent text-white dark:text-background"
      : "border border-line bg-surface text-muted hover:border-accent/60");
  return (
    <>
      {founder && (
        <div role="tablist" aria-label="Which report" className="flex gap-2">
          <button type="button" role="tab" aria-selected={tab === "product"} onClick={() => setTab("product")} className={tabClass(tab === "product")}>
            Product brief
          </button>
          <button type="button" role="tab" aria-selected={tab === "founder"} onClick={() => setTab("founder")} className={tabClass(tab === "founder")}>
            Founder brief
          </button>
        </div>
      )}
      {founder && tab === "founder" ? <FounderView briefId={id} /> : <ProductBrief id={id} brief={brief} />}
    </>
  );
}

function ProductBrief({ id, brief }: { id: string; brief: Brief }) {
  return (
    <>
      <p className="text-xl leading-snug">{brief.one_liner}</p>
      <Journeys id={id} siteUrl={brief.url} journeys={brief.suggested_journeys ?? []} />
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">What it is</h2>
        <dl className="space-y-4">
          <Field label="What it does" value={brief.what_it_does} />
          <Field label="Who it&apos;s for" value={brief.who_its_for} />
          <Field label="How it works" value={brief.how_it_works} />
          <Field label="The main thing a user gets" value={brief.primary_value} />
        </dl>
      </section>
      <Pricing pricing={brief.pricing} />
      <BusinessModel model={brief.business_model} />
      <Claims claims={brief.claims ?? []} />
      <Unknowns unknowns={brief.unknowns ?? []} />
      <PagesRead brief={brief} />
      <p className="text-sm text-muted">
        This brief is written from the public pages listed above and nothing else. Marketing claims are goals to
        test, not proof that the product does them.
      </p>
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  const unknown = !value || value === "unknown";
  return (
    <div>
      <dt className="text-sm font-medium text-subtle">{label}</dt>
      <dd className={unknown ? "text-subtle" : "text-foreground"}>{unknown ? "Unknown: the site doesn't say." : value}</dd>
    </div>
  );
}

// The main call to action: each journey is editable in place, and "Test this journey" opens the test
// form with the URL, the goal and the success condition as they are now.
function Journeys({ id, siteUrl, journeys }: { id: string; siteUrl: string; journeys: SuggestedJourney[] }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Goals worth testing</h2>
        <p className="mt-1 text-sm text-muted">
          Taken from the site&apos;s own calls to action and claims. Edit one, then test it with a first-time visitor.
        </p>
      </div>
      {journeys.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
          The pages we read gave nothing specific enough to suggest a goal. You can still{" "}
          <Link href={testJourneyHref(id, siteUrl, "", "")} className="font-medium text-accent hover:underline">
            write your own goal
          </Link>
          .
        </p>
      ) : (
        <ul className="space-y-4">
          {journeys.map((journey, index) => (
            <Journey key={`${index}-${journey.goal}`} id={id} siteUrl={siteUrl} journey={journey} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Journey({ id, siteUrl, journey }: { id: string; siteUrl: string; journey: SuggestedJourney }) {
  const [goal, setGoal] = useState(journey.goal);
  const [success, setSuccess] = useState(journey.success);
  const fieldClass =
    "mt-1 block w-full rounded-lg border border-line bg-background px-3 py-2 text-base text-foreground focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30";
  return (
    <li className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div>
        <label className="text-sm font-medium text-subtle">
          Goal
          <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={2} maxLength={500} className={fieldClass} />
        </label>
      </div>
      <div>
        <label className="text-sm font-medium text-subtle">
          Success looks like
          <textarea value={success} onChange={(event) => setSuccess(event.target.value)} rows={2} maxLength={300} className={fieldClass} />
        </label>
      </div>
      <p className="text-sm text-muted">
        {journey.claim_to_test ? "A claim to test, not proof that it works: " : "A call to action on the site: "}
        <q>{journey.basis_text}</q> (<SourceLink url={journey.source_url} />)
      </p>
      <Link
        href={testJourneyHref(id, siteUrl, goal, success)}
        className="inline-block rounded-lg bg-accent px-4 py-2 font-medium text-white hover:bg-accent-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 dark:text-background"
      >
        Test this journey
      </Link>
    </li>
  );
}

const PRICING_LABEL: Record<Brief["pricing"]["status"], string> = {
  published: "Published",
  not_published: "Not published",
  unclear: "Unclear",
};

function Pricing({ pricing }: { pricing: Brief["pricing"] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">Pricing</h2>
      <p>
        <span className="rounded-full bg-surface px-2.5 py-0.5 text-sm font-medium ring-1 ring-line">
          {PRICING_LABEL[pricing.status] ?? "Unclear"}
        </span>
      </p>
      {pricing.status !== "published" && pricing.note && <p className="text-muted">{pricing.note}</p>}
      {pricing.tiers.length > 0 && (
        <ul className="space-y-3">
          {pricing.tiers.map((tier, index) => (
            <li key={`${index}-${tier.name}`} className="rounded-xl border border-line bg-surface p-4">
              <p className="font-medium">
                {tier.name} <span className="text-muted">· {tier.price}</span>
              </p>
              {tier.what_you_get && tier.what_you_get !== "unknown" && <p className="mt-1 text-muted">{tier.what_you_get}</p>}
              <p className="mt-1 text-sm text-subtle">
                Source: <SourceLink url={tier.source_url} />
              </p>
            </li>
          ))}
        </ul>
      )}
      {pricing.note && pricing.status === "published" && <p className="text-sm text-muted">{pricing.note}</p>}
    </section>
  );
}

function BusinessModel({ model }: { model: Brief["business_model"] }) {
  const unknown = !model.model || model.model === "unknown";
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">
        Business model <span className="text-base font-normal text-subtle">(inferred)</span>
      </h2>
      <p className={unknown ? "text-subtle" : ""}>
        {unknown ? "Unknown: the pages give no evidence." : model.model}
      </p>
      {model.evidence.length > 0 && (
        <ul className="space-y-2 text-sm text-muted">
          {model.evidence.map((item, index) => (
            <li key={index}>
              <q>{item.quote}</q> (<SourceLink url={item.source_url} />)
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const STATUS_LABEL: Record<ClaimStatus, { label: string; tone: string }> = {
  confirmed: { label: "Stated on the site", tone: "bg-success-soft text-success" },
  inferred: { label: "Inferred", tone: "bg-warning-soft text-warning" },
  unknown: { label: "Unknown", tone: "bg-surface text-subtle ring-1 ring-line" },
};

function Claims({ claims }: { claims: BriefClaim[] }) {
  if (claims.length === 0) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">What the site claims</h2>
      <ul className="space-y-3">
        {sortClaims(claims).map((claim, index) => {
          const status = STATUS_LABEL[claim.status] ?? STATUS_LABEL.unknown;
          return (
            <li key={index} className="rounded-xl border border-line bg-surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${status.tone}`}>{status.label}</span>
                <p className="font-medium">{claim.claim}</p>
              </div>
              {claim.quote && <p className="mt-2 text-sm text-muted"><q>{claim.quote}</q></p>}
              <p className="mt-1 text-sm text-subtle">
                Source: <SourceLink url={claim.source_url} />
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Unknowns({ unknowns }: { unknowns: string[] }) {
  if (unknowns.length === 0) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">What we couldn&apos;t confirm</h2>
      <ul className="list-disc space-y-1 pl-5 text-muted">
        {unknowns.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function PagesRead({ brief }: { brief: Brief }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">Pages read</h2>
      <ul className="space-y-1 text-sm text-muted">
        {brief.pages.map((page) => (
          <li key={page.url}>
            <span className="text-subtle">{page.kind}: </span>
            <SourceLink url={page.url} />
            {page.method === "browser" && <span className="text-subtle"> (needed a browser)</span>}
          </li>
        ))}
      </ul>
      {brief.skipped.length > 0 && (
        <div>
          <p className="text-sm font-medium text-subtle">Not read</p>
          <ul className="mt-1 space-y-1 text-sm text-muted">
            {brief.skipped.map((item, index) => (
              <li key={index}>
                <SourceLink url={item.url} /> — {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
