import type { Metadata } from "next";
import Link from "next/link";

import { grid } from "@/lib/css";
import { BUILT_WITH, EXAMPLE_REPORT_HREF, SOCIAL } from "@/lib/site";

export const metadata: Metadata = {
  title: "About · First User",
  description: "First User was built solo by Divyanshu Verma (DV) at #neatHack.",
};

const LINKS = [SOCIAL.x, SOCIAL.linkedin, SOCIAL.github, SOCIAL.repo];

export default function AboutPage() {
  return (
    <main className="relative isolate" style={{ padding: "var(--page-top-lg) var(--gutter) var(--section-y)" }}>
      <div
        aria-hidden
        className="fu-dots inset-x-0 top-0 h-[620px]"
        style={{
          WebkitMaskImage: "radial-gradient(ellipse 60% 70% at 30% 15%, #000 20%, transparent 75%)",
          maskImage: "radial-gradient(ellipse 60% 70% at 30% 15%, #000 20%, transparent 75%)",
        }}
      />
      <h1 className="fu-display flex flex-col text-giant" style={{ lineHeight: 0.84, letterSpacing: "-.015em" }}>
        <span className="fu-line">
          <span>First User</span>
        </span>
        <span className="fu-line" style={{ padding: ".06em 0" }}>
          <span>
            <span className="fu-mark" style={{ padding: "0 14px", borderRadius: 14 }}>
              #neatHack
            </span>
          </span>
        </span>
        <span className="fu-line">
          <span className="text-ink4">· neatlogs</span>
        </span>
      </h1>

      <div data-reveal="" data-self="0" className="fu-grid items-start" style={grid("320px", "clamp(32px,5cqi,72px)", { marginTop: "clamp(56px,7cqi,88px)" })}>
        <div
          data-stagger=""
          aria-hidden
          className="flex aspect-[4/5] w-full max-w-[420px] -rotate-2 flex-col justify-between rounded-hero border-[1.5px] border-ink bg-acc p-7 text-on-acc shadow-hard-xl transition-transform duration-500 ease-bounce hover:-translate-y-1.5 hover:rotate-0"
        >
          <div className="flex items-center justify-between">
            <span className="font-code text-[12px] font-medium uppercase tracking-[.1em]">Built solo</span>
            <span className="flex h-[22px] w-[30px] items-center justify-center overflow-hidden rounded-[9px] bg-ink-fixed">
              <span className="size-1.5 rounded-full bg-acc-fixed" style={{ animation: "fuLook 6s ease-in-out infinite" }} />
            </span>
          </div>
          <span className="fu-display text-[clamp(140px,17cqi,230px)]" style={{ lineHeight: 0.8 }}>
            DV
          </span>
          <span className="text-[14px] font-medium">Divyanshu Verma</span>
        </div>
        <div className="flex flex-col gap-9">
          <div data-stagger="" className="flex flex-col gap-[18px]">
            <p className="m-0 text-[clamp(24px,2.8cqi,36px)] leading-[1.3] tracking-[-.01em] fu-pretty">
              Built solo by Divyanshu Verma (DV) at #neatHack.
            </p>
            <p className="m-0 max-w-[36em] text-[17px] leading-[1.55] text-ink2 fu-pretty">
              First User sends a first-time visitor through your product before real users arrive, and reports honestly what
              happened: what worked, where it got stuck, and what it couldn&apos;t confirm.
            </p>
          </div>
          <ul data-stagger="" className="m-0 flex list-none flex-col gap-2.5 p-0">
            {LINKS.map((link) => (
              <li key={link.label}>
                <a
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="fu-lift flex min-h-[68px] items-center gap-4 rounded-panel border-[1.5px] border-ink bg-s1 py-3 pl-5 pr-3.5 hover:bg-acc-soft hover:text-ink"
                >
                  <span className="w-20 flex-none font-code text-[12px] font-medium uppercase tracking-[.08em] text-ink3">{link.label}</span>
                  <span className="min-w-0 flex-1 text-[clamp(16px,1.8cqi,20px)] font-medium [overflow-wrap:anywhere]">{link.handle}</span>
                  <span aria-hidden className="flex size-[38px] flex-none items-center justify-center rounded-full border-[1.5px] border-ink bg-acc text-ink-fixed">
                    ↗
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <div data-stagger="" className="flex flex-col gap-3.5">
            <span className="fu-eyebrow">Built with</span>
            <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
              {BUILT_WITH.map((name) => (
                <li key={name} className="flex h-11 items-center whitespace-nowrap rounded-pill border-[1.5px] border-ink bg-s1 px-[18px] text-[15px] font-semibold transition-transform duration-200 hover:-rotate-3 hover:scale-105 hover:bg-acc-soft">
                  {name}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div data-reveal="" data-self="0" className="fu-grid" style={grid("300px", "14px", { marginTop: "clamp(64px,8cqi,96px)" })}>
        <Link
          data-stagger=""
          href="/journey"
          className="fu-lift fu-lift-lg flex min-h-[200px] flex-col gap-7 rounded-form border-[1.5px] border-ink bg-deep text-white hover:text-white"
          style={{ padding: "clamp(22px,3cqi,32px)" }}
        >
          <span className="font-code text-[12px] font-medium uppercase tracking-[.08em] text-acc-fixed">Build journey</span>
          <span className="fu-display mt-auto text-link-card" style={{ fontStretch: "70%", lineHeight: 0.95 }}>
            v0 to v6, mistakes included →
          </span>
        </Link>
        <Link
          data-stagger=""
          href={EXAMPLE_REPORT_HREF}
          className="fu-lift fu-lift-lg flex min-h-[200px] flex-col gap-7 rounded-form border-[1.5px] border-ink bg-acc text-on-acc hover:text-on-acc"
          style={{ padding: "clamp(22px,3cqi,32px)" }}
        >
          <span className="font-code text-[12px] font-medium uppercase tracking-[.08em]">Example report</span>
          <span className="fu-display mt-auto text-link-card" style={{ fontStretch: "70%", lineHeight: 0.95 }}>
            See what lands after a run →
          </span>
        </Link>
      </div>
    </main>
  );
}
