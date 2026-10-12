"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { grid } from "@/lib/css";
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
    <div className="flex flex-col" style={{ gap: "clamp(36px,5cqi,56px)" }}>
      <p className="m-0 rounded-frame border-[1.5px] border-ink bg-amber-soft px-5 py-4 text-[16px] font-medium leading-normal text-amber-ink">
        {FOUNDER_NOTE}
      </p>
      {state.kind === "loading" && (
        <p role="status" className="m-0 font-code text-[13px] text-ink3">
          Loading…
        </p>
      )}
      {(state.kind === "none" || failed) && (
        <section className="fu-card-sm flex flex-col gap-3 p-6">
          {failed && (
            <p role="alert" className="m-0 text-[15px] text-bad-ink">
              {failure ?? "That one didn't finish."}
            </p>
          )}
          <p className="m-0 text-[16px] leading-normal text-ink2">
            The founder brief is written on request from the product brief. It reads nothing new from the site.
          </p>
          <button type="button" onClick={ask} disabled={asking} className="fu-btn fu-btn-md self-start">
            {asking ? "Asking…" : failed ? "Try again" : "Write the founder brief"}
          </button>
          {message && (
            <p role="alert" className="m-0 text-[15px] text-bad-ink">
              {message}
            </p>
          )}
        </section>
      )}
      {state.kind === "run" && (state.run.status === "queued" || state.run.status === "running") && (
        <section role="status" className="fu-card-sm flex flex-col gap-2 p-6">
          <span className="flex items-center gap-2 font-code text-[12px] font-medium uppercase tracking-[.06em] text-ink3">
            <span aria-hidden className="size-2 rounded-full bg-pass" style={{ animation: "fuBlink 1.6s ease-in-out infinite" }} />
            {state.run.status === "queued" ? "Waiting for a free worker" : "Writing the founder brief"}
          </span>
          <p className="m-0 text-[15px] text-ink2">This page updates by itself.</p>
        </section>
      )}
      {state.kind === "run" && state.run.status === "done" && isFounderBrief(state.run.brief) && <Report brief={state.run.brief} />}
    </div>
  );
}

function Sources({ sources: all }: { sources: FounderSource[] }) {
  // One link per page, even for a brief saved before the worker did this.
  const sources = all.filter((source, index) => all.findIndex((other) => other.url === source.url) === index);
  if (sources.length === 0) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
      {sources.map((source, index) => (
        <SourceLink key={`${source.url}-${index}`} url={source.url} />
      ))}
    </span>
  );
}

function Tag({ item }: { item: FounderStatement }) {
  return item.status === "assessment" ? (
    <span className="fu-chip fu-chip-tag ml-2 border-dashed border-ink3 bg-s2 align-middle text-ink2">{ASSESSMENT_LABEL}</span>
  ) : null;
}

function Statement({ label, item }: { label?: string; item: FounderStatement }) {
  const unknown = item.status === "unknown";
  return (
    <div className="flex flex-col gap-1 border-b border-line py-3">
      {label && <dt className="font-code text-[12px] font-medium uppercase tracking-[.04em] text-ink3">{label}</dt>}
      <dd className={`m-0 text-[16px] leading-[1.55] ${unknown ? "text-ink3" : ""}`}>
        {unknown ? "Unknown: the pages don't say." : item.text}
        <Tag item={item} />
        <Sources sources={item.sources} />
      </dd>
    </div>
  );
}

function StatementList({ items, empty }: { items: FounderStatement[]; empty: string }) {
  if (items.length === 0) return <p className="m-0 text-[15px] text-ink3">{empty}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {items.map((item, index) => (
        <li key={index} className="text-[15px] leading-normal">
          {item.text}
          <Tag item={item} />
          <Sources sources={item.sources} />
        </li>
      ))}
    </ul>
  );
}

// One section of the founder brief: its heading on the left, its content on the right.
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="fu-grid border-t-[1.5px] border-ink pt-[22px]" style={grid("280px", "12px clamp(20px,3cqi,40px)")}>
      <h2 className="fu-display fu-display-wide text-founder" style={{ lineHeight: 1 }}>
        {title}
      </h2>
      <div className="flex min-w-0 flex-col gap-4">{children}</div>
    </section>
  );
}

function SubHead({ children }: { children: ReactNode }) {
  return <h3 className="m-0 flex flex-wrap items-center gap-1 font-code text-[12px] font-medium uppercase tracking-[.06em] text-ink3">{children}</h3>;
}

function Report({ brief }: { brief: FounderBrief }) {
  const summary = brief.executive_summary;
  const opportunity = brief.opportunity;
  const product = brief.product_and_business_model;
  const evidence = brief.evidence_and_risks;
  const risks = [
    ["technical", "Technical"],
    ["competitive", "Competitive"],
    ["go_to_market", "Go-to-market"],
  ] as const;
  const riskItems = risks.flatMap(([key, title]) => evidence.risks[key].map((item) => ({ title, item })));
  return (
    <>
      <Section title="Executive summary">
        <dl className="m-0">
          <Statement label="What the company is building" item={summary.building} />
          <Statement label="For whom" item={summary.for_whom} />
          <Statement label="The problem" item={summary.problem} />
          <Statement label="The solution" item={summary.solution} />
          <Statement label="The business model (inferred)" item={summary.business_model} />
        </dl>
      </Section>

      <Section title="The opportunity">
        <dl className="m-0">
          <Statement label="The problem" item={opportunity.problem} />
          <div className="flex flex-col gap-1 border-b border-line py-3">
            <dt className="font-code text-[12px] font-medium uppercase tracking-[.04em] text-ink3">Alternatives the site names</dt>
            <dd className="m-0 text-[16px] leading-[1.55]">
              {opportunity.alternatives.length === 0 ? (
                <span className="text-ink3">Unknown: the pages name none.</span>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {opportunity.alternatives.map((alternative, index) => (
                    <li key={index}>
                      {alternative.name}
                      <Sources sources={alternative.sources} />
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
          <Statement label="Target users" item={opportunity.target_users} />
          <Statement label="Why it may be different" item={opportunity.why_different} />
        </dl>
      </Section>

      <Section title="Product and business model">
        <div className="flex flex-col gap-2">
          <SubHead>Core features</SubHead>
          <StatementList items={product.core_features} empty="Unknown: the pages don't list any." />
        </div>
        <div className="flex flex-col gap-2">
          <SubHead>Maturity signals</SubHead>
          <StatementList items={product.maturity_signals} empty="None shown on the pages read." />
        </div>
        <div className="flex flex-col gap-2">
          <SubHead>Pricing</SubHead>
          {product.pricing.status === "published" && product.pricing.tiers.length > 0 ? (
            <ul className="m-0 flex list-none flex-col p-0">
              {product.pricing.tiers.map((tier, index) => (
                <li key={index} className="flex flex-wrap items-center justify-between gap-3 border-t border-line py-2">
                  <span className="text-[15px] font-semibold">{tier.name}</span>
                  <span className="flex items-center gap-3">
                    <span className="font-code text-[14px]">{tier.price}</span>
                    <SourceLink url={tier.source_url} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[15px] text-ink3">
              {product.pricing.status === "not_published" ? "Not published." : "Unclear."} {product.pricing.note}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <SubHead>
            How it appears to make money
            <span className="fu-chip fu-chip-tag ml-1 border-dashed border-ink bg-amber-soft text-amber-ink">Inferred</span>
          </SubHead>
          <p className={`m-0 text-[16px] leading-normal ${product.business_model.model === "unknown" ? "text-ink3" : ""}`}>
            {product.business_model.model === "unknown" ? "Unknown." : product.business_model.model}
          </p>
          {product.business_model.evidence.map((item, index) => (
            <div key={index} className="fu-quote">
              <span className="text-[14px] text-ink2">&ldquo;{item.quote}&rdquo;</span>
              <SourceLink url={item.source_url} />
            </div>
          ))}
        </div>
      </Section>

      <section className="flex flex-col gap-3.5 border-t-[1.5px] border-ink pt-[22px]">
        <h2 className="fu-display fu-display-wide text-founder" style={{ lineHeight: 1 }}>
          Evidence and risks
        </h2>
        <div className="fu-grid" style={grid("300px", "12px")}>
          {evidence.traction.map((item, index) => (
            <div key={`t-${index}`} className="flex flex-col gap-2.5 rounded-panel border-[1.5px] border-ink bg-s1 p-[18px]">
              <span className="fu-chip fu-chip-tag self-start border-none bg-amber-soft text-amber-ink">{TRACTION_LABEL}</span>
              <span className="text-[16px] font-semibold leading-[1.45]">{item.claim}</span>
              <div className="fu-quote">
                <span className="text-[14px] leading-normal text-ink2">&ldquo;{item.quote}&rdquo;</span>
                <SourceLink url={item.source_url} />
              </div>
            </div>
          ))}
          {riskItems.map(({ title, item }, index) => (
            <div key={`r-${index}`} className="flex flex-col gap-2.5 rounded-panel border-[1.5px] border-dashed border-ink bg-s1 p-[18px]">
              <span className="fu-chip fu-chip-tag self-start border-none bg-s2 text-ink2">
                {ASSESSMENT_LABEL} · {title}
              </span>
              <span className="text-[16px] font-semibold leading-[1.45]">{item.text}</span>
              <Sources sources={item.sources} />
            </div>
          ))}
        </div>
        {evidence.traction.length === 0 && <p className="m-0 text-[15px] text-ink3">No traction is stated on the pages read.</p>}
        {riskItems.length === 0 && <p className="m-0 text-[15px] text-ink3">No risks noted from the pages read.</p>}
        <div className="flex flex-col gap-2 rounded-panel border-[1.5px] border-dashed border-ink3 p-[18px]">
          <SubHead>Evidence that is missing</SubHead>
          {evidence.missing_evidence.length === 0 ? (
            <p className="m-0 text-[15px] text-ink3">Nothing listed.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {evidence.missing_evidence.map((item, index) => (
                <li key={index} className="text-[15px] leading-normal text-ink2">
                  · {item}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="flex flex-col gap-3.5 border-t-[1.5px] border-ink pt-[22px]">
        <div className="flex flex-col gap-1.5">
          <h2 className="fu-display fu-display-wide text-founder" style={{ lineHeight: 1 }}>
            Readiness
          </h2>
          <p className="m-0 text-[15px] text-ink2">
            Six separate questions, not a grade. Each shows what the public evidence says, what it doesn&apos;t, and what you
            should be ready to answer.
          </p>
        </div>
        <ul className="fu-grid m-0 list-none p-0" style={grid("340px")}>
          {brief.readiness.map((dimension) => (
            <li key={dimension.dimension} className="fu-card-sm flex flex-col gap-3.5 p-5">
              <h3 className="m-0 text-[18px] font-semibold">{dimension.label}</h3>
              <div className="flex flex-col gap-1.5">
                <span className="fu-eyebrow-sm">What the public evidence shows</span>
                <StatementList items={dimension.shows} empty="Nothing on the pages read shows this." />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="fu-eyebrow-sm">Unknown</span>
                {dimension.unknown.length === 0 ? (
                  <span className="text-[15px] text-ink3">Nothing listed.</span>
                ) : (
                  <ul className="m-0 flex list-none flex-col gap-1 p-0">
                    {dimension.unknown.map((item, index) => (
                      <li key={index} className="text-[15px] leading-normal text-ink2">
                        {item}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="mt-auto rounded-field border border-ink bg-acc-soft px-3.5 py-3 text-[15px] leading-normal">
                <span className="font-semibold">Be ready to answer: </span>
                {dimension.question}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
