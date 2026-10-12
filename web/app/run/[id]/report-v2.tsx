"use client";

// Report v2: the verdict, the three answers, the evidence labels and the run facts. Kept in its own file
// so the report page can show or hide each one by flag (lib/report-flags.ts).

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { grid } from "@/lib/css";
import { HIDDEN_TEXT_NOTICE, hiddenTextNotice, withoutNotice } from "@/lib/hidden-text";
import { BASIS_LABEL, BASIS_NOTE, fixFirst, shortUrl, understanding, withoutPromises } from "@/lib/report-logic";
import { isHttpUrl, pathOf } from "@/lib/report-view";
import type { ReportFlags } from "@/lib/report-flags";
import type { Basis, FirstImpression, Clarity, Run, Step, VerdictKind } from "@/lib/types";
import { derivedHeadline, VERDICT_LOOK } from "@/lib/verdict-look";

import { againHref, BrowserFrame } from "./report-bits";

// ------------------------------------------------------------------------------------- evidence labels

const BASIS_SHORT: Record<Basis, string> = { observed: "Observed", verified: "Verified", recommendation: "Our recommendation" };

// A small label saying what a statement rests on. Hidden with the labels flag.
export function BasisBadge({ basis, show = true, short = false }: { basis: Basis; show?: boolean; short?: boolean }) {
  if (!show) return null;
  return (
    <span
      title={BASIS_NOTE[basis]}
      className="fu-chip fu-chip-tag border-current"
      style={{ borderStyle: basis === "recommendation" ? "dashed" : "solid", borderColor: "currentColor" }}
    >
      {short ? BASIS_SHORT[basis] : BASIS_LABEL[basis]}
    </span>
  );
}

// ------------------------------------------------------------------------------------- the verdict hero

// The six states' colours and labels live in lib/verdict-look.ts, shared with the brief and the home page.
export { VERDICT_LOOK };

const OUTCOME_LABEL: Record<string, string> = {
  achieved: "Reached the goal",
  achieved_unconfirmed: "Reached the goal, not independently confirmed",
  not_achieved: "Did not reach the goal",
  unverified: "Said it reached the goal, but we could not confirm it",
  blocked: "Got blocked",
  gave_up: "Gave up",
  max_steps: "Ran out of steps",
  error: "Didn't finish",
};

const QUOTE_BY: Partial<Record<VerdictKind, string>> = {
  got_through: "Independent check",
  unconfirmed: "What the check couldn't see",
};

const DEFAULT_WAYS = [
  { t: "Start link", d: "Share a demo or guest page that opens inside the product. The visit begins there." },
  { t: "Test login", d: "A throwaway account. Never shown to the AI, deleted after the run." },
  { t: "Let it sign up", d: "The visitor creates its own account. Not possible with Google or GitHub sign-in only." },
];

// The hero's title: the verdict's own headline, the same words for an older run, or with the verdict
// switched off the old outcome label.
export function heroTitle(run: Run, steps: Step[], kind: VerdictKind, flags: ReportFlags): string {
  if (run.status === "failed") return derivedHeadline("our_failure", "");
  const verdict = flags.verdict ? run.verdict : null;
  if (verdict) return verdict.headline;
  if (flags.verdict) {
    const lastUrl = [...steps].reverse().find((step) => step.url)?.url ?? null;
    const page = pathOf(lastUrl);
    return derivedHeadline(kind, page && page !== "/" ? page : "");
  }
  return (run.entry?.bot_check ? "Blocked by a bot check" : OUTCOME_LABEL[run.outcome ?? "error"]) ?? "Didn't finish";
}

export function VerdictHero({
  run,
  steps,
  kind,
  flags,
  loginHelp,
}: {
  run: Run;
  steps: Step[];
  kind: VerdictKind;
  flags: ReportFlags;
  loginHelp: boolean;
}) {
  const look = VERDICT_LOOK[kind];
  const verdict = flags.verdict ? run.verdict : null;
  const failed = run.status === "failed";
  const title = heroTitle(run, steps, kind, flags);

  // The screenshot shown beside the verdict: where it happened, else the last one taken.
  const atStep = verdict?.where_step != null ? steps.find((step) => step.idx === verdict.where_step && isHttpUrl(step.screenshot_path)) : null;
  const shot = atStep ?? [...steps].reverse().find((step) => isHttpUrl(step.screenshot_path)) ?? null;

  const ways = verdict?.kind === "login_wall" && verdict.ways_in?.length ? verdict.ways_in : null;
  const showWays = kind === "login_wall" || loginHelp;
  const style: CSSProperties = { background: look.bg, color: look.fg, borderStyle: look.border };

  return (
    <div className="flex flex-col gap-3">
      <section
        id="fu-r-verdict"
        aria-labelledby="verdict-title"
        className="fu-grid overflow-hidden rounded-hero border-[1.5px] border-ink shadow-hard-xl"
        style={grid("380px", "0px", style)}
      >
        <div className="flex flex-col gap-[18px]" style={{ padding: "clamp(24px,4cqi,44px)" }}>
          <span
            className="flex h-7 items-center gap-2 self-start whitespace-nowrap rounded-pill px-3 font-code text-[12px] font-medium uppercase tracking-[.06em]"
            style={{ background: look.chipBg, color: look.chipFg }}
          >
            <span aria-hidden className="size-1.5 rounded-full bg-current" />
            {look.label}
          </span>
          <h1 id="verdict-title" className="fu-display text-verdict" style={{ textWrap: "balance", overflowWrap: "anywhere" }}>
            {title}
          </h1>
          {failed ? (
            <p className="m-0 max-w-[52ch] text-[clamp(16px,1.6cqi,19px)] leading-normal fu-pretty">
              Something went wrong on our side, so this tells you nothing about your site.
              {steps.length > 0 && " The steps recorded before it stopped are below."}
            </p>
          ) : (
            verdict?.detail &&
            verdict.kind !== "unconfirmed" && (
              <p className="m-0 max-w-[52ch] text-[clamp(16px,1.6cqi,19px)] leading-normal fu-pretty">{verdict.detail}</p>
            )
          )}
          {verdict?.evidence_quote && (
            <blockquote className="m-0 flex flex-col gap-1.5 rounded-frame border-[1.5px] border-ink bg-s1 px-[18px] py-3.5 text-ink">
              <span className="fu-eyebrow-sm flex flex-wrap items-center gap-2">
                {QUOTE_BY[verdict.kind] ?? "Evidence"}
                <BasisBadge basis={verdict.basis} show={flags.labels} />
              </span>
              <span className="text-[16px] font-medium leading-normal">{verdict.evidence_quote}</span>
            </blockquote>
          )}
          {(verdict?.where_step != null || verdict?.where_url) && (
            <p className="m-0 text-[15px]">
              {verdict.where_step != null && (
                <a href={`#step-${verdict.where_step}`} className="fu-link">
                  Step {verdict.where_step}
                </a>
              )}
              {verdict.where_step != null && verdict.where_url ? " on " : ""}
              {verdict.where_url ? shortUrl(verdict.where_url) : ""}
            </p>
          )}
          {!failed && run.reason && run.outcome !== "achieved" && (
            <div className="flex flex-col gap-1 text-[15px] leading-normal">
              <span className="fu-eyebrow-sm" style={{ color: "inherit", opacity: 0.8 }}>
                The visitor&apos;s own report
              </span>
              <span className="fu-pretty">{run.reason}</span>
            </div>
          )}
          {flags.success && !failed && (
            <p className="m-0 text-[14px] leading-normal" style={{ opacity: 0.85 }}>
              {run.success_condition ? (
                <>
                  <span className="font-semibold">Success condition you gave: </span>
                  {run.success_condition}
                </>
              ) : (
                "The goal was checked without a stated success condition."
              )}
            </p>
          )}
          {kind === "our_failure" && (
            <Link href={againHref(run)} className="fu-btn fu-btn-md self-start">
              Run it again →
            </Link>
          )}
        </div>
        <div className="flex flex-col justify-center gap-2.5" style={{ padding: "clamp(16px,3cqi,32px)", background: "color-mix(in srgb, var(--ink) 6%, transparent)" }}>
          {shot ? (
            <>
              <span className="fu-eyebrow-sm" style={{ color: "inherit" }}>
                {atStep ? "Where it happened" : "Final screenshot"} · step {shot.idx}
              </span>
              <BrowserFrame url={shot.url} rounded="frame">
                <a href={shot.screenshot_path as string} target="_blank" rel="noopener noreferrer">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={shot.screenshot_path as string} alt={`The page at step ${shot.idx}`} className="fu-browser-shot" />
                </a>
              </BrowserFrame>
            </>
          ) : (
            <div className="flex min-h-[190px] items-center justify-center rounded-frame border-[1.5px] border-dashed border-current p-6 text-center text-[15px]" style={{ opacity: 0.8 }}>
              No screenshot was recorded for this visit.
            </div>
          )}
        </div>
      </section>

      {showWays && (
        <div className="fu-grid" style={grid("240px", "12px")}>
          {ways
            ? ways.map((way, index) => (
                <div key={index} className="fu-lift flex flex-col gap-2 rounded-panel border-[1.5px] border-ink bg-s1 p-[18px]">
                  <span className="fu-eyebrow-sm">Way in {index + 1}</span>
                  <span className="text-[15px] leading-[1.45] text-ink2">{way}</span>
                </div>
              ))
            : DEFAULT_WAYS.map((way, index) => (
                <div key={way.t} className="fu-lift flex flex-col gap-2 rounded-panel border-[1.5px] border-ink bg-s1 p-[18px]">
                  <span className="text-[17px] font-semibold">{way.t}</span>
                  <span className="text-[14px] leading-[1.45] text-ink2">
                    {way.d}
                    {index === 0 && run.start_url && " (You gave one this time.)"}
                    {index === 1 && run.entry?.test_login === "failed" && " (The one you gave this time did not work.)"}
                    {index === 2 && run.entry?.self_signup === "blocked_verification" && " (Your signup needs email verification.)"}
                  </span>
                </div>
              ))}
          <Link href={againHref(run)} className="fu-btn fu-btn-md self-center justify-self-start">
            Start a deeper run →
          </Link>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------- the short answer

const LEVEL_CHIP = {
  clear: { bg: "var(--green-soft)", fg: "var(--green-ink)" },
  partly: { bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  unclear: { bg: "var(--bad-soft)", fg: "var(--bad-ink)" },
};

function AnswerCard({
  question,
  chip,
  answer,
  note,
  basis,
  showBasis,
}: {
  question: string;
  chip?: { text: string; bg: string; fg: string };
  answer: ReactNode;
  note?: ReactNode;
  basis: Basis;
  showBasis: boolean;
}) {
  return (
    <div data-stagger="" className="fu-card-sm fu-lift flex flex-col gap-3 p-[22px]">
      <span className="text-[14px] font-medium text-ink3">{question}</span>
      {chip && (
        <span
          className="flex h-[26px] items-center self-start whitespace-nowrap rounded-pill border border-ink px-2.5 text-[12px] font-semibold"
          style={{ background: chip.bg, color: chip.fg }}
        >
          {chip.text}
        </span>
      )}
      {/* A long answer (the review's own words) is set smaller, so the three cards stay readable side by side. */}
      <span
        className={`font-semibold leading-[1.35] fu-pretty ${typeof answer === "string" && answer.length > 90 ? "text-[16px]" : "text-[19px]"}`}
      >
        {answer}
      </span>
      {note && <div className="border-t border-line pt-3 text-[14px] leading-normal text-ink2">{note}</div>}
      <div className="mt-auto">
        <BasisBadge basis={basis} show={showBasis} short />
      </div>
    </div>
  );
}

// Will they understand it? Can they get value? What to fix first? Answered from the first impression,
// the verdict and the top finding.
export function ShortAnswer({ run, kind, title, showBasis }: { run: Run; kind: VerdictKind; title: string; showBasis: boolean }) {
  const understood = understanding(run.first_impression);
  const verdict = run.verdict;
  // A bot check or a failure on our side says nothing about the site, with or without a stored verdict.
  const first = kind === "bot_check" || kind === "our_failure" ? ({ state: "not_about_site" } as const) : fixFirst(run.findings, verdict);
  const look = VERDICT_LOOK[kind];
  return (
    <section id="fu-r-short" data-reveal="" data-self="0" aria-labelledby="short-answer" className="flex flex-col gap-[18px]">
      <div data-stagger="" className="flex flex-col gap-2.5">
        <span className="fu-eyebrow">01 · Summary</span>
        <h2 id="short-answer" className="fu-display fu-display-mid text-block" style={{ lineHeight: 0.95 }}>
          The short answer
        </h2>
      </div>
      <div className="fu-grid" style={grid("260px", "12px")}>
        <AnswerCard
          question="Will a new user understand it?"
          chip={understood ? { text: understood.label, ...LEVEL_CHIP[understood.level] } : undefined}
          answer={
            understood
              ? (understood.reasons[0] ?? "What it does, who it is for and the main action were all clear on the landing page.")
              : "Not assessed"
          }
          note={
            understood && understood.reasons.length > 1 ? (
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {understood.reasons.slice(1, 3).map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
            ) : !understood ? (
              "The landing page could not be reviewed."
            ) : undefined
          }
          basis="observed"
          showBasis={showBasis}
        />
        <AnswerCard
          question="Can they get value?"
          chip={{ text: look.label, bg: look.bg, fg: look.fg }}
          answer={title}
          basis={verdict?.basis ?? "observed"}
          showBasis={showBasis}
        />
        <AnswerCard
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
          note={
            first.state === "finding" ? (
              <a href="#fu-r-find" className="fu-link">
                Ranked first of the findings below
              </a>
            ) : first.state === "none" ? (
              "Nothing in this visit stood out as a problem with your site."
            ) : first.state === "not_about_site" ? (
              "This visit says nothing about your site, so there is nothing to fix from it."
            ) : undefined
          }
          basis={first.state === "finding" ? "recommendation" : "observed"}
          showBasis={showBasis}
        />
      </div>
      {showBasis && (
        <p className="m-0 text-[13px] leading-normal text-ink3">
          Each answer is labelled by what it rests on. <strong>Observed</strong>: from the record of the visit.{" "}
          <strong>Verified</strong>: confirmed by an independent check. <strong>Our recommendation</strong>: our suggestion,
          not a measured result.
        </p>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------------- first impression

const CLARITY: Record<Clarity, { text: string; obvious: string; bg: string; fg: string }> = {
  yes: { text: "Clear", obvious: "Obvious", ...LEVEL_CHIP.clear },
  partly: { text: "Partly clear", obvious: "Somewhat obvious", ...LEVEL_CHIP.partly },
  no: { text: "Not clear", obvious: "Not obvious", ...LEVEL_CHIP.unclear },
};

// What a newcomer sees on the landing page without logging in. Collapsed under the short answer; open
// when the short answer is switched off, since then this is the only place it shows.
export function FirstImpressionPanel({ review, flags, open }: { review: FirstImpression; flags: ReportFlags; open: boolean }) {
  const rows: [string, Clarity | undefined, string | undefined, boolean][] = [
    ["What it does", review.what_it_does?.clear, review.what_it_does?.summary, false],
    ["Who it is for", review.who_its_for?.clear, review.who_its_for?.summary, false],
    ["The main action", review.main_action?.obvious, review.main_action?.summary, true],
  ];
  const hesitations = withoutNotice(review.hesitations);
  const suggestions = (review.suggestions ?? []).map(withoutPromises).filter(Boolean);
  return (
    <details open={open} className="overflow-hidden rounded-card border-[1.5px] border-ink bg-s1">
      <summary className="flex min-h-[72px] items-center justify-between gap-4 px-6 py-[18px]">
        <span className="flex flex-col gap-1">
          <span className="fu-eyebrow-sm flex flex-wrap items-center gap-2">
            First impression <BasisBadge basis="observed" show={flags.labels} short />
          </span>
          <span className="text-[19px] font-semibold">What a newcomer sees on the landing page</span>
        </span>
        <span aria-hidden className="fu-plus size-9">
          +
        </span>
      </summary>
      <div className="flex flex-col gap-5 px-6 pb-6">
        <dl className="m-0 fu-grid" style={grid("240px", "12px 32px")}>
          {rows.map(([label, level, summary, obvious]) => {
            const chip = level && CLARITY[level];
            return (
              <div key={label} className="flex flex-col gap-1.5 border-t border-line pt-3">
                <dt className="flex flex-wrap items-center gap-2 font-code text-[12px] font-medium uppercase tracking-[.04em] text-ink3">
                  {label}
                  {chip && (
                    <span className="rounded-pill px-2 py-0.5 font-sans text-[12px] font-semibold normal-case tracking-normal" style={{ background: chip.bg, color: chip.fg }}>
                      {obvious ? chip.obvious : chip.text}
                    </span>
                  )}
                </dt>
                {summary && <dd className="m-0 text-[15px] leading-normal">{summary}</dd>}
              </div>
            );
          })}
        </dl>
        {hesitations.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="m-0 text-[16px] font-semibold">What might make a newcomer hesitate</h3>
            <ul className="m-0 flex flex-col gap-1.5 pl-5 text-[15px] leading-normal text-ink2">
              {hesitations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {suggestions.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="m-0 flex flex-wrap items-center gap-2 text-[16px] font-semibold">
              Suggestions <BasisBadge basis="recommendation" show={flags.labels} short />
            </h3>
            <ol className="m-0 flex flex-col gap-1.5 pl-5 text-[15px] leading-normal">
              {suggestions.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </details>
  );
}

// ------------------------------------------------------------------------------------- hidden text

// One small line when the page hid instructions aimed at AI agents. The wording is the page's own fixed copy of
// the worker's notice, and the hiding methods are fixed labels: nothing the page hid is ever shown.
export function HiddenTextLine({ run }: { run: Run }) {
  const notice = hiddenTextNotice(run.hidden_text, run.first_impression);
  if (!notice) return null;
  return (
    <p role="note" className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-field border-[1.5px] border-dashed border-ink3 bg-s1 px-4 py-3 text-[14px] leading-normal text-ink2">
      <span className="fu-chip fu-chip-tag border-none bg-s2 text-ink2">Hidden text</span>
      <span className="min-w-0 flex-1">
        {HIDDEN_TEXT_NOTICE}
        {notice.methods.length > 0 && <span className="text-ink3"> Hidden as {notice.methods.join(", ")}.</span>}
      </span>
    </p>
  );
}
