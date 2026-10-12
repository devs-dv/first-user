import type { Metadata } from "next";

import { HEADLINE, LESSONS, MILESTONES, SINGLE_RUNS } from "@/content/journey";
import { X_POSTS } from "@/content/x-posts";
import { grid } from "@/lib/css";
import { SOCIAL } from "@/lib/site";

import { ByTool, XPosts } from "./journey-client";

export const metadata: Metadata = {
  title: "Build Journey · First User",
  description: "Building First User at #neatHack, in public: what broke at each version, and what changed because of it.",
};

export default function JourneyPage() {
  const singleRuns = SINGLE_RUNS.filter((run) => run.result.trim());
  return (
    <main className="relative isolate" style={{ padding: "var(--page-top-lg) var(--gutter) var(--section-y)" }}>
      <div
        aria-hidden
        className="fu-dots inset-x-0 top-0 h-[620px]"
        style={{
          WebkitMaskImage: "radial-gradient(ellipse 60% 70% at 25% 20%, #000 20%, transparent 75%)",
          maskImage: "radial-gradient(ellipse 60% 70% at 25% 20%, #000 20%, transparent 75%)",
        }}
      />
      <span className="fu-pill-tag">
        <span className="fu-dot-live" />
        /journey · Building in public
      </span>
      <h1 className="fu-display mt-[22px] flex flex-col text-journey" style={{ lineHeight: 0.86, letterSpacing: "-.01em" }}>
        <span className="fu-line">
          <span>Building</span>
        </span>
        <span className="fu-line">
          <span>First User</span>
        </span>
        <span className="fu-line" style={{ padding: ".06em 0" }}>
          <span>
            <span className="text-ink4">in</span> <span className="fu-mark">neatHack</span>
          </span>
        </span>
      </h1>
      <div className="fu-grid mt-9 items-end" style={grid("320px", "24px")}>
        <p className="m-0 max-w-[34em] text-lede-sm leading-normal text-ink2 fu-pretty">
          From the first agent to 7 of 7 verified, two rounds in a row. What broke at each step, and what changed because of it.
        </p>
        <div className="flex flex-wrap gap-2.5">
          <div className="min-w-[150px] flex-1 rounded-panel border-[1.5px] border-ink bg-s1 px-[18px] py-4">
            <span className="fu-eyebrow-sm block">{HEADLINE.before.label}</span>
            <span className="fu-display text-[48px]" style={{ lineHeight: 1 }}>
              {HEADLINE.before.value}
            </span>
            <span className="block text-[13px] text-ink3">{HEADLINE.before.note}</span>
          </div>
          <div className="min-w-[150px] flex-1 rounded-panel border-[1.5px] border-ink bg-acc px-[18px] py-4 text-on-acc">
            <span className="block font-code text-[11px] font-medium uppercase tracking-[.08em]">{HEADLINE.after.label}</span>
            <span className="fu-display text-[48px]" style={{ lineHeight: 1 }}>
              {HEADLINE.after.value}
            </span>
            <span className="block text-[13px]">{HEADLINE.after.note}</span>
          </div>
        </div>
      </div>

      <div className="relative" style={{ marginTop: "clamp(64px,8cqi,104px)", paddingLeft: "clamp(36px,5cqi,64px)" }}>
        <div data-scrub-y="" aria-hidden className="absolute bottom-0 left-2 top-0 w-[3px] overflow-hidden rounded-[3px] bg-line">
          <span className="absolute inset-0 origin-top bg-acc" style={{ transform: "scaleY(0)" }} />
        </div>
        <ol className="m-0 flex list-none flex-col p-0" style={{ gap: "clamp(20px,3cqi,32px)" }}>
          {MILESTONES.map((milestone) => (
            <li key={milestone.version} data-reveal="" className="relative">
              <span
                data-mdot=""
                aria-hidden
                className="absolute top-7 size-[17px] rounded-full border-[1.5px] border-ink bg-s1 transition-[background,transform] duration-300"
                style={{ left: "calc(-1 * clamp(36px,5cqi,64px) + 1.5px)" }}
              />
              <article
                className="fu-lift fu-lift-lg fu-grid rounded-form border-[1.5px] border-ink"
                style={grid("280px", "18px clamp(20px,3cqi,40px)", {
                  padding: "clamp(20px,3cqi,32px)",
                  background: milestone.highlight === "v6" ? "var(--acc-soft)" : "var(--s1)",
                })}
              >
                <div className="flex flex-col gap-2.5">
                  <span className="fu-display text-mile" style={{ lineHeight: 0.85, color: milestone.highlight === "today" ? "var(--pass)" : "var(--ink)" }}>
                    {milestone.version}
                  </span>
                  <h2 className="m-0 text-[clamp(20px,2.2cqi,26px)] font-semibold leading-[1.25] fu-pretty">{milestone.title}</h2>
                  <a
                    href={milestone.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-auto flex h-[34px] items-center gap-1.5 self-start rounded-pill border border-ink px-3 font-code text-[12px] font-medium transition-colors hover:bg-acc hover:text-ink-fixed"
                  >
                    Entire checkpoint ↗
                  </a>
                </div>
                <div className="flex flex-col gap-2.5">
                  <div className="flex flex-col gap-1.5 rounded-frame border border-line bg-bad-soft p-4">
                    <span className="fu-eyebrow-sm text-bad-ink">✕ What broke</span>
                    <span className="text-[15px] leading-normal">{milestone.broke}</span>
                  </div>
                  <div className="flex flex-col gap-1.5 rounded-frame border border-line bg-green-soft p-4">
                    <span className="fu-eyebrow-sm text-green-ink">✓ What changed</span>
                    <span className="text-[15px] leading-normal">{milestone.changed}</span>
                  </div>
                </div>
              </article>
            </li>
          ))}
        </ol>
      </div>

      {singleRuns.length > 0 && (
        <section data-reveal="" className="flex flex-col gap-4" style={{ marginTop: "var(--section-y)" }}>
          <span className="fu-eyebrow">Single runs · not a benchmark</span>
          <div className="fu-grid" style={grid("320px")}>
            {singleRuns.map((run) => (
              <article key={run.title} className="flex flex-col gap-3 rounded-card border-[1.5px] border-dashed border-ink bg-s1 p-[22px]">
                <span className="fu-chip fu-chip-tag self-start">One run</span>
                <h3 className="m-0 text-[19px] font-semibold">{run.title}</h3>
                <p className="m-0 text-[15px] leading-normal text-ink2">{run.what}</p>
                <p className="m-0 text-[15px] leading-normal">{run.result}</p>
                {run.link && (
                  <a href={run.link} className="fu-link text-[14px]">
                    Open the report
                  </a>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      <ByTool />

      <section data-reveal="" data-self="0" className="flex flex-col gap-7" style={{ marginTop: "var(--section-y)" }}>
        <div data-stagger="">
          <span className="fu-eyebrow mb-3.5 block">Mistakes included</span>
          <h2 className="fu-display text-section">Lessons learned</h2>
        </div>
        <ol className="fu-grid m-0 list-none p-0" style={grid("280px")}>
          {LESSONS.map((lesson, index) => (
            <li key={lesson.title} data-stagger="" className="fu-card fu-lift flex min-h-[200px] flex-col gap-3 p-[22px]">
              <div className="flex items-center justify-between gap-2">
                <span className="font-code text-[13px] font-medium text-ink3">0{index + 1}</span>
                <span
                  className="fu-chip fu-chip-tag border-none"
                  style={lesson.mistake ? { background: "var(--bad)", color: "var(--on-bad)" } : { background: "var(--s2)", color: "var(--ink2)" }}
                >
                  {lesson.mistake ? "Mistake" : "Lesson"}
                </span>
              </div>
              <h3 className="m-0 text-[19px] font-semibold leading-[1.3]">{lesson.title}</h3>
              <p className="m-0 text-[15px] leading-[1.55] text-ink2 fu-pretty">{lesson.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section style={{ marginTop: "var(--section-y)" }}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="fu-display text-section">On X</h2>
          <a href={SOCIAL.x.href} target="_blank" rel="noopener noreferrer" className="fu-btn fu-btn-outline h-10 px-4 text-[14px] font-medium">
            Follow {SOCIAL.x.handle} ↗
          </a>
        </div>
        <XPosts days={X_POSTS} />
      </section>
    </main>
  );
}
