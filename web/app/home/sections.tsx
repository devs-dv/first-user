"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState, type MouseEvent } from "react";

import { grid } from "@/lib/css";
import { FORM_ANCHOR } from "@/lib/site";

import { goToForm } from "../site-header";
import { copyText } from "../copy";
import { BROKEN_CASES, FAQ, LOOP, TRUST, WHO } from "./data";
import { setHome, useHome } from "./store";

function useGoToForm() {
  const pathname = usePathname();
  const router = useRouter();
  return (event: MouseEvent) => {
    setHome({ tab: "test" });
    goToForm(event, pathname, router.push);
  };
}

function SectionHead({ eyebrow, children, night = false }: { eyebrow: string; children: React.ReactNode; night?: boolean }) {
  return (
    <div data-stagger="">
      <span className="fu-eyebrow mb-4 block" style={night ? { color: "var(--acc-fixed)" } : undefined}>
        {eyebrow}
      </span>
      <h2 className="fu-display text-section">{children}</h2>
    </div>
  );
}

const DEMO_PROMPT =
  'What to change: Only clear the form after the create request succeeds. If it fails, keep the input and show the error next to the button.\nAcceptance: One click creates the project. It appears in the dashboard.\nRetest: Create "Launch plan" once.';

// ------------------------------------------------------------------------------------- 02 demo run
export function DemoRun() {
  const [copied, setCopied] = useState(false);
  return (
    <section id="fu-real" data-reveal="" data-self="0" className="fu-section relative isolate border-t border-line bg-bg">
      <div
        aria-hidden
        className="fu-dots inset-0 opacity-60"
        style={{
          backgroundImage: "radial-gradient(var(--off) 1.1px, transparent 1.1px)",
          WebkitMaskImage: "linear-gradient(transparent, #000 30%, #000 70%, transparent)",
          maskImage: "linear-gradient(transparent, #000 30%, #000 70%, transparent)",
        }}
      />
      <div className="mb-10 flex flex-wrap items-end justify-between gap-x-10 gap-y-5">
        <SectionHead eyebrow="02 · Demo run">
          One run,
          <br />
          start to fix.
        </SectionHead>
        <div data-stagger="" className="flex flex-col items-start gap-3">
          <span className="fu-chip fu-chip-dashed">Demo · an illustrative run on a made-up site</span>
          <span className="font-code text-[13px] font-medium text-ink3">taskpond.app · start link · 14 steps</span>
        </div>
      </div>
      <div data-scrub="" aria-hidden className="relative mb-5 h-[3px] overflow-hidden rounded-[3px] bg-line">
        <span className="absolute inset-0 origin-left border-r-[1.5px] border-ink bg-acc" style={{ transform: "scaleX(0)" }} />
      </div>
      <div className="fu-grid items-stretch" style={grid("300px", "16px")}>
        <div data-stagger="" className="fu-card fu-lift fu-lift-lg flex flex-col gap-4" style={{ padding: "var(--card-pad-lg)" }}>
          <StepHead n={1} label="Goal" />
          <p className="m-0 text-[clamp(22px,2.4cqi,28px)] font-semibold leading-[1.25] fu-pretty">
            Create a project and add the first task.
          </p>
          <div className="fu-panel bg-s1">
            <span className="fu-eyebrow-sm">Success looks like</span>
            <span className="text-[15px] leading-[1.45]">A project appears in the dashboard.</span>
          </div>
          <div className="mt-auto flex flex-wrap gap-1.5">
            <span className="fu-chip">Start link</span>
            <span className="fu-chip">Real browser</span>
          </div>
        </div>
        <div data-stagger="" className="fu-card fu-lift fu-lift-lg flex flex-col gap-4" style={{ padding: "var(--card-pad-lg)" }}>
          <StepHead n={2} label="What the agent observed" />
          <div aria-hidden className="fu-browser relative">
            <div className="fu-browser-bar">
              <span className="fu-browser-dot" />
              taskpond.app/projects/new
              <span className="ml-auto flex h-[18px] items-center rounded px-1.5" style={{ background: "#FDE3DF", color: "#9A2214" }}>
                Step 6
              </span>
            </div>
            <div className="relative flex flex-col gap-2 p-4">
              <span className="text-[14px] font-semibold text-page-ink">New project</span>
              <span className="flex h-[30px] items-center rounded-md border border-page-line2 px-2 text-[12px] text-page-ink2">Launch plan</span>
              <span
                className="relative flex h-[30px] items-center gap-1.5 self-start rounded-md bg-page-btn px-3 text-[12px] text-white"
                style={{ animation: "fuRing 3s ease-out infinite" }}
              >
                <span
                  className="size-2.5 rounded-full border-2 border-white/40"
                  style={{ borderTopColor: "#FFFFFF", animation: "fuSpin .8s linear infinite" }}
                />
                Create project
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 22 22"
                  className="absolute left-[70%] top-[55%]"
                  style={{ animation: "fuTap 3s ease-in-out infinite", filter: "drop-shadow(0 2px 3px rgba(0,0,0,.25))" }}
                >
                  <path d="M2 2l7 18 2.6-7.4L19 10z" fill="#0E1320" stroke="#FFFFFF" strokeWidth="1.5" strokeLinejoin="round" />
                </svg>
              </span>
            </div>
          </div>
          <p className="m-0 text-[15px] leading-normal text-ink2">
            &ldquo;Create project&rdquo; showed a spinner, then the form stayed on screen with no message.
          </p>
          <div className="mt-auto flex flex-wrap gap-1.5">
            <span className="fu-chip fu-chip-word" style={{ background: "var(--bad)", color: "var(--on-bad)" }}>
              High
            </span>
            <span className="fu-chip fu-chip-tag border-ink" style={{ height: 26 }}>
              Verified
            </span>
            <span className="fu-chip">Seen again · 8, 11</span>
          </div>
        </div>
        <div data-stagger="" className="fu-card fu-lift fu-lift-lg flex flex-col gap-4" style={{ padding: "var(--card-pad-lg)" }}>
          <StepHead n={3} label="The fix it recommends" />
          <div className="fu-code flex flex-1 flex-col gap-3 rounded-field p-4 text-[13px]">
            <span data-line="" className="block">
              <span className="text-acc-fixed">What to change</span>
              <br />
              Only clear the form after the create request succeeds. If it fails, keep the input and show the error next to the
              button.
            </span>
            <span data-line="" className="block">
              <span className="text-acc-fixed">Acceptance</span>
              <br />☐ One click creates the project
              <br />☐ It appears in the dashboard
            </span>
            <span data-line="" className="block">
              <span className="text-acc-fixed">Retest</span>
              <br />
              Create &ldquo;Launch plan&rdquo; once.
            </span>
          </div>
          <button
            type="button"
            className="fu-btn"
            onClick={async () => {
              if (await copyText(DEMO_PROMPT)) {
                setCopied(true);
                setTimeout(() => setCopied(false), 1600);
              }
            }}
          >
            <span aria-live="polite">{copied ? "Copied ✓" : "Copy fix prompt"}</span>
          </button>
        </div>
      </div>
    </section>
  );
}

function StepHead({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex size-[30px] flex-none items-center justify-center rounded-full border-[1.5px] border-ink bg-acc text-[13px] font-bold text-ink-fixed">
        {n}
      </span>
      <span className="fu-eyebrow">{label}</span>
    </div>
  );
}

// ------------------------------------------------------------------------------------- 03 how it works
export function HowItWorks() {
  const step = useHome((s) => s.step);
  const on = Math.floor(step / 2) % 4;
  return (
    <section id="fu-how" data-reveal="" className="fu-section border-t border-line bg-s1">
      <div>
        <span className="fu-eyebrow mb-4 block">03 · How it works</span>
        <h2 className="fu-display mb-9 text-section-sm">How it works</h2>
      </div>
      <ol className="fu-grid m-0 list-none p-0" style={grid("240px")}>
        {LOOP.map((item, i) => (
          <li
            key={item.name}
            className="fu-card-sm fu-lift flex min-h-[220px] flex-col gap-3 p-6"
            style={{ background: i === on ? "var(--acc-soft)" : "var(--s1)" }}
          >
            <div className="flex items-center justify-between">
              <span className="font-code text-[13px] font-medium text-ink3">0{i + 1}</span>
              <span
                aria-hidden
                className="size-2.5 rounded-full border-[1.5px] border-ink"
                style={{ background: i === on ? "var(--acc)" : "transparent", transition: "background .4s" }}
              />
            </div>
            <span className="font-display text-[32px] font-extrabold uppercase leading-none" style={{ fontStretch: "75%" }}>
              {item.name}
            </span>
            <p className="m-0 text-[15px] leading-normal text-ink2 fu-pretty">{item.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ------------------------------------------------------------------------------------- 04 trust
export function Trust() {
  return (
    <section data-reveal="" className="fu-section border-t border-line bg-bg">
      <div className="fu-grid items-start" style={grid("340px", "clamp(24px,4cqi,56px)")}>
        <div>
          <span className="fu-eyebrow mb-4 block">04 · Trust</span>
          <h2 className="fu-display text-section-sm">
            Why trust
            <br />
            the report
          </h2>
        </div>
        <ul className="m-0 flex list-none flex-col border-t-[1.5px] border-ink p-0">
          {TRUST.map((line) => (
            <li
              key={line}
              className="-mx-3 grid gap-3 rounded-field border-b border-line px-3 py-[18px] transition-colors hover:bg-s1"
              style={{ gridTemplateColumns: "44px minmax(0,1fr)" }}
            >
              <span aria-hidden className="flex size-7 items-center justify-center rounded-full border-[1.5px] border-ink bg-acc text-[13px] font-semibold text-ink-fixed">
                ✓
              </span>
              <span className="text-[18px] font-medium leading-[1.45] fu-pretty">{line}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------- 05 results
// From evals/results/v6.md and v6b.md: 7 of 7 achievable cases completed and verified in both rounds,
// 0 of 3 broken sites praised, and a total cost of $0.0747 for 10 runs in v6 (under 1 cent a run).
export function Results() {
  const card = "flex flex-col gap-5 rounded-card border border-night-line bg-night-s1 px-6 py-7 transition-[border-color,transform] duration-300 hover:-translate-y-1 hover:border-acc-fixed";
  const big = "fu-display text-stat text-acc-fixed";
  return (
    <section data-reveal="" data-self="0" className="fu-section relative isolate bg-night text-white">
      <div
        aria-hidden
        className="absolute -right-[10%] -top-[30%] -z-10 aspect-square w-[60%] rounded-full blur-[20px]"
        style={{ background: "radial-gradient(circle, rgba(198,255,61,.12), transparent 65%)" }}
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-10"
        style={{
          backgroundImage: "radial-gradient(#22262D 1.2px, transparent 1.2px)",
          backgroundSize: "22px 22px",
          WebkitMaskImage: "linear-gradient(#000, transparent 85%)",
          maskImage: "linear-gradient(#000, transparent 85%)",
        }}
      />
      <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
        <SectionHead eyebrow="05 · Results" night>
          Results
        </SectionHead>
        <span data-stagger="" className="flex h-[30px] items-center whitespace-nowrap rounded-pill border border-night-line2 px-3 font-code text-[12px] font-medium text-[#C8CCD3]">
          Measured on v6, two rounds
        </span>
      </div>
      <div className="fu-grid" style={grid("300px")}>
        <div data-stagger="" className={card}>
          <span data-count="7" data-suf="/7" className={big} style={{ lineHeight: 0.82 }}>
            7/7
          </span>
          <div aria-hidden className="flex flex-col gap-2">
            {["Round 1", "Round 2"].map((label) => (
              <div key={label} className="flex items-center gap-2.5">
                <span className="w-16 flex-none font-code text-[11px] font-medium text-night-ink3">{label}</span>
                <div className="grid flex-1 grid-cols-7 gap-1">
                  {Array.from({ length: 7 }, (_, i) => (
                    <span key={i} data-pop="" className="h-[18px] rounded-[5px] border border-ink-fixed bg-acc-fixed" />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <span className="mt-auto text-[16px] leading-normal text-night-ink2 fu-pretty">
            7 of 7 test journeys completed and independently verified, in two consecutive rounds.
          </span>
        </div>
        <div data-stagger="" className={card}>
          <span data-count="0" data-from="3" data-suf="/3" className={big} style={{ lineHeight: 0.82 }}>
            0/3
          </span>
          <div aria-hidden className="grid grid-cols-3 gap-1.5">
            {BROKEN_CASES.map((name) => (
              <div key={name} data-pop="" className="flex min-w-0 flex-col gap-1.5 rounded-r10 border border-dashed border-night-line2 p-2.5">
                <span className="truncate font-code text-[11px] font-medium text-night-ink3">{name}</span>
                <span className="text-[12px] font-semibold text-[#FF7A6B]">✕ Not praised</span>
              </div>
            ))}
          </div>
          <span className="mt-auto text-[16px] leading-normal text-night-ink2">0 of 3 broken sites praised.</span>
        </div>
        <div data-stagger="" className={card}>
          <span className={big} style={{ lineHeight: 0.82 }}>
            &lt;1¢
          </span>
          <div aria-hidden className="flex flex-col gap-2">
            <div data-scrub="" className="relative h-[18px] overflow-hidden rounded-md border border-night-line2 bg-night">
              <span className="absolute inset-0 max-w-[75%] origin-left bg-acc-fixed" style={{ transform: "scaleX(0)" }} />
            </div>
            <div className="flex justify-between font-code text-[11px] font-medium text-night-ink3">
              <span>0¢</span>
              <span>1¢</span>
            </div>
          </div>
          <span className="mt-auto text-[16px] leading-normal text-night-ink2">Under 1 cent per run, on average.</span>
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------- 06 who it's for
export function WhoItsFor() {
  const go = useGoToForm();
  return (
    <section data-reveal="" data-self="0" style={{ padding: "var(--section-y) var(--gutter) 0" }}>
      <div className="fu-grid items-start" style={grid("340px", "clamp(24px,4cqi,56px)")}>
        <div data-stagger="" className="flex flex-col gap-[18px]">
          <div>
            <span className="fu-eyebrow mb-4 block">06 · Who it&apos;s for</span>
            <h2 className="fu-display text-section">
              Who it&apos;s
              <br />
              for
            </h2>
          </div>
          <p className="m-0 max-w-[28em] text-[17px] leading-normal text-ink2">
            Anyone about to show a product to strangers for the first time.
          </p>
        </div>
        <div className="flex flex-col border-t-[1.5px] border-ink">
          {WHO.map((who, i) => (
            <a
              key={who}
              href={`/#${FORM_ANCHOR}`}
              data-stagger=""
              onClick={go}
              className="fu-who grid w-full items-center gap-3 border-b border-ink px-4 text-left text-ink"
              style={{ gridTemplateColumns: "48px minmax(0,1fr) 44px", minHeight: "clamp(84px,9cqi,112px)" }}
            >
              <span className="font-code text-[13px] font-medium opacity-70">0{i + 1}</span>
              <span className="fu-display fu-display-mid text-who" style={{ fontWeight: 800, lineHeight: 0.95 }}>
                {who}
              </span>
              <span aria-hidden className="flex size-10 items-center justify-center rounded-full border-[1.5px] border-current text-[16px]">
                →
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------- 07 FAQ
export function Faq() {
  const [open, setOpen] = useState(-1);
  return (
    <section
      data-reveal=""
      className="border-t border-line bg-s1"
      style={{ marginTop: "var(--section-y)", padding: "clamp(64px,8cqi,96px) var(--gutter)" }}
    >
      <div className="fu-grid items-start" style={grid("340px", "clamp(24px,4cqi,56px)")}>
        <div>
          <span className="fu-eyebrow mb-4 block">07 · Questions</span>
          <h2 className="fu-display text-section-sm">FAQ</h2>
        </div>
        <div className="flex flex-col border-t-[1.5px] border-ink">
          {FAQ.map((item, i) => (
            <div key={item.q} className="border-b border-line">
              <button
                type="button"
                aria-expanded={open === i}
                aria-controls={`faq-${i}`}
                onClick={() => setOpen(open === i ? -1 : i)}
                className="flex min-h-16 w-full cursor-pointer items-center justify-between gap-4 border-none bg-transparent py-4 text-left text-[18px] font-semibold text-ink"
              >
                {item.q}
                <span aria-hidden className="fu-plus">
                  +
                </span>
              </button>
              {open === i && (
                <p id={`faq-${i}`} className="m-0 mb-5 max-w-[56ch] text-[16px] leading-[1.55] text-ink2">
                  {item.a}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------- final call to action
export function FinalCta() {
  const go = useGoToForm();
  return (
    <section
      data-reveal=""
      className="relative flex flex-col items-center gap-7 overflow-hidden rounded-hero border-[1.5px] border-ink bg-acc text-center text-on-acc shadow-hard-xl"
      style={{ margin: "clamp(56px,7cqi,88px) var(--gutter)", padding: "clamp(36px,6cqi,72px) var(--gutter)" }}
    >
      <h2 className="fu-display text-cta" style={{ lineHeight: 0.86 }}>
        Meet your
        <br />
        first user.
      </h2>
      <p className="m-0 max-w-[34em] text-[18px] leading-normal">One goal, one real browser, one honest report. A few minutes.</p>
      <a
        href={`/#${FORM_ANCHOR}`}
        onClick={go}
        className="fu-btn fu-btn-dark h-14 gap-3 pl-[26px] pr-2 text-[16px] hover:shadow-[0_5px_0_#FFFFFF]"
      >
        Test my website
        <span aria-hidden className="fu-arrow fu-arrow-acc size-10">
          →
        </span>
      </a>
    </section>
  );
}
