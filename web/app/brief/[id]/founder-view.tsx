"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ASSESSMENT_LABEL,
  FOUNDER_NOTE,
  TRACTION_LABEL,
  isFounderBrief,
  isFounderFailure,
  type FounderBrief,
  type FounderRun,
  type FounderSource,
  type FounderStatement,
} from "@/lib/founder-types";

import { SourceLink } from "./source-link";

const POLL_MS = 2000;

type State = { kind: "loading" } | { kind: "none" } | { kind: "run"; run: FounderRun };

export function FounderView({ briefId }: { briefId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const response = await fetch(`/api/briefs/${encodeURIComponent(briefId)}/founder`, { cache: "no-store" });
        if (cancelled) return;
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const { run } = (await response.json()) as { run: FounderRun | null };
        if (cancelled) return;
        setState(run ? { kind: "run", run } : { kind: "none" });
        if (run && (run.status === "queued" || run.status === "running")) timer = setTimeout(load, POLL_MS);
      } catch {
        if (!cancelled) timer = setTimeout(load, POLL_MS * 2);
      }
    }
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [briefId, tick]);

  const ask = useCallback(async () => {
    setAsking(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/briefs/${encodeURIComponent(briefId)}/founder`, { method: "POST" });
      const body = (await response.json().catch(() => null)) as { message?: string } | null;
      if (response.ok) setTick((n) => n + 1);
      else setMessage(body?.message ?? "Something went wrong on our side. Please try again in a minute.");
    } catch {
      setMessage("Couldn't reach the server. Check your connection and try again.");
    }
    setAsking(false);
  }, [briefId]);

  const failed = state.kind === "run" && state.run.status === "failed";
  const failure = state.kind === "run" && isFounderFailure(state.run.brief) ? state.run.brief.message : null;
  return (
    <div className="space-y-10">
      <p className="rounded-xl border border-line bg-surface p-4 text-sm font-medium">{FOUNDER_NOTE}</p>
      {state.kind === "loading" && <p className="text-muted">Loading…</p>}
      {(state.kind === "none" || failed) && (
        <section className="space-y-3 rounded-xl border border-line bg-surface p-5">
          {failed && (
            <p role="alert" className="text-sm text-danger">
              {failure ?? "That one didn't finish."}
            </p>
          )}
          <p className="text-muted">
            The founder brief is written on request from the product brief. It reads nothing new from the site.
          </p>
          <button
            type="button"
            onClick={ask}
            disabled={asking}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:bg-accent-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 disabled:opacity-60 dark:text-background"
          >
            {asking ? "Asking…" : failed ? "Try again" : "Write the founder brief"}
          </button>
          {message && (
            <p role="alert" className="text-sm text-danger">
              {message}
            </p>
          )}
        </section>
      )}
      {state.kind === "run" && (state.run.status === "queued" || state.run.status === "running") && (
        <section role="status" className="rounded-xl border border-line bg-surface p-5">
          <p className="font-medium">
            {state.run.status === "queued" ? "Waiting for a free worker" : "Writing the founder brief"}
          </p>
          <p className="mt-2 text-sm text-muted">This page updates by itself.</p>
        </section>
      )}
      {state.kind === "run" && state.run.status === "done" && isFounderBrief(state.run.brief) && (
        <Report brief={state.run.brief} />
      )}
    </div>
  );
}

function Sources({ sources: all }: { sources: FounderSource[] }) {
  // One link per page, even for a brief saved before the worker did this.
  const sources = all.filter((source, index) => all.findIndex((other) => other.url === source.url) === index);
  if (sources.length === 0) return null;
  return (
    <span className="text-sm text-subtle">
      {" ("}
      {sources.map((source, index) => (
        <span key={`${source.url}-${index}`}>
          {index > 0 && ", "}
          <SourceLink url={source.url} />
        </span>
      ))}
      {")"}
    </span>
  );
}

function Tag({ item }: { item: FounderStatement }) {
  return item.status === "assessment" ? <span className="ml-2 text-sm text-subtle">{ASSESSMENT_LABEL}</span> : null;
}

function Statement({ label, item }: { label?: string; item: FounderStatement }) {
  const unknown = item.status === "unknown";
  return (
    <div>
      {label && <dt className="text-sm font-medium text-subtle">{label}</dt>}
      <dd className={unknown ? "text-subtle" : ""}>
        {unknown ? "Unknown: the pages don't say." : item.text}
        <Sources sources={item.sources} />
        <Tag item={item} />
      </dd>
    </div>
  );
}

function StatementList({ items, empty }: { items: FounderStatement[]; empty: string }) {
  if (items.length === 0) return <p className="text-subtle">{empty}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item, index) => (
        <li key={index}>
          {item.text}
          <Sources sources={item.sources} />
          <Tag item={item} />
        </li>
      ))}
    </ul>
  );
}

function Report({ brief }: { brief: FounderBrief }) {
  const summary = brief.executive_summary;
  const opportunity = brief.opportunity;
  const product = brief.product_and_business_model;
  const evidence = brief.evidence_and_risks;
  const risks = [
    ["technical", "Technical risks"],
    ["competitive", "Competitive risks"],
    ["go_to_market", "Go-to-market risks"],
  ] as const;
  return (
    <>
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Executive summary</h2>
        <dl className="space-y-4">
          <Statement label="What the company is building" item={summary.building} />
          <Statement label="For whom" item={summary.for_whom} />
          <Statement label="The problem" item={summary.problem} />
          <Statement label="The solution" item={summary.solution} />
          <Statement label="The business model (inferred)" item={summary.business_model} />
        </dl>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">The opportunity</h2>
        <dl className="space-y-4">
          <Statement label="The problem" item={opportunity.problem} />
          <div>
            <dt className="text-sm font-medium text-subtle">Alternatives the site names</dt>
            <dd>
              {opportunity.alternatives.length === 0 ? (
                <span className="text-subtle">Unknown: the pages name none.</span>
              ) : (
                opportunity.alternatives.map((alternative, index) => (
                  <span key={index}>
                    {index > 0 && ", "}
                    {alternative.name}
                    <Sources sources={alternative.sources} />
                  </span>
                ))
              )}
            </dd>
          </div>
          <Statement label="Target users" item={opportunity.target_users} />
          <Statement label="Why it may be different" item={opportunity.why_different} />
        </dl>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Product and business model</h2>
        <div>
          <h3 className="mb-1 text-sm font-medium text-subtle">Core features</h3>
          <StatementList items={product.core_features} empty="Unknown: the pages don't list any." />
        </div>
        <div>
          <h3 className="mb-1 text-sm font-medium text-subtle">Maturity signals</h3>
          <StatementList items={product.maturity_signals} empty="None shown on the pages read." />
        </div>
        <div>
          <h3 className="mb-1 text-sm font-medium text-subtle">Pricing</h3>
          {product.pricing.status === "published" && product.pricing.tiers.length > 0 ? (
            <ul className="space-y-1">
              {product.pricing.tiers.map((tier, index) => (
                <li key={index}>
                  {tier.name} · {tier.price}
                  <Sources sources={[{ url: tier.source_url, quote: "" }]} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-subtle">
              {product.pricing.status === "not_published" ? "Not published." : "Unclear."} {product.pricing.note}
            </p>
          )}
        </div>
        <div>
          <h3 className="mb-1 text-sm font-medium text-subtle">How it appears to make money (inferred)</h3>
          <p className={product.business_model.model === "unknown" ? "text-subtle" : ""}>
            {product.business_model.model === "unknown" ? "Unknown." : product.business_model.model}
          </p>
          {product.business_model.evidence.length > 0 && (
            <ul className="mt-1 space-y-1 text-sm text-muted">
              {product.business_model.evidence.map((item, index) => (
                <li key={index}>
                  <q>{item.quote}</q> (<SourceLink url={item.source_url} />)
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Evidence and risks</h2>
        <div>
          <h3 className="mb-1 text-sm font-medium text-subtle">Traction the company states</h3>
          {evidence.traction.length === 0 ? (
            <p className="text-subtle">None stated on the pages read.</p>
          ) : (
            <ul className="space-y-3">
              {evidence.traction.map((item, index) => (
                <li key={index} className="rounded-xl border border-line bg-surface p-4">
                  <p className="text-sm font-medium text-warning">{TRACTION_LABEL}</p>
                  <p className="mt-1">{item.claim}</p>
                  <p className="mt-1 text-sm text-muted">
                    <q>{item.quote}</q> (<SourceLink url={item.source_url} />)
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="mb-1 text-sm font-medium text-subtle">Evidence that is missing</h3>
          {evidence.missing_evidence.length === 0 ? (
            <p className="text-subtle">Nothing listed.</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-muted">
              {evidence.missing_evidence.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          )}
        </div>
        {risks.map(([key, title]) => (
          <div key={key}>
            <h3 className="mb-1 text-sm font-medium text-subtle">
              {title} <span className="font-normal">({ASSESSMENT_LABEL})</span>
            </h3>
            <StatementList items={evidence.risks[key]} empty="None noted from the pages read." />
          </div>
        ))}
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Readiness, dimension by dimension</h2>
        <p className="text-sm text-muted">
          Six separate questions, not a grade. Each shows what the public evidence says, what it doesn&apos;t, and
          what you should be ready to answer.
        </p>
        <ul className="space-y-4">
          {brief.readiness.map((dimension) => (
            <li key={dimension.dimension} className="space-y-3 rounded-xl border border-line bg-surface p-4">
              <h3 className="font-semibold">{dimension.label}</h3>
              <div>
                <p className="text-sm font-medium text-subtle">What the public evidence shows</p>
                <StatementList items={dimension.shows} empty="Nothing on the pages read shows this." />
              </div>
              <div>
                <p className="text-sm font-medium text-subtle">What is unknown</p>
                {dimension.unknown.length === 0 ? (
                  <p className="text-subtle">Nothing listed.</p>
                ) : (
                  <ul className="list-disc space-y-1 pl-5 text-muted">
                    {dimension.unknown.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-subtle">Be ready to answer</p>
                <p>{dimension.question}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
