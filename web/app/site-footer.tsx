"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { MouseEvent } from "react";

import { grid } from "@/lib/css";
import { FORM_ANCHOR, NAV_ITEMS, SOCIAL } from "@/lib/site";

import { reducedMotion } from "./motion";
import { goToForm } from "./site-header";

const WORDMARK = "FIRST USER".split("");

// The big letters at the bottom rise and turn green near the pointer.
function wordmarkMove(event: MouseEvent<HTMLDivElement>) {
  if (reducedMotion()) return;
  const x = event.clientX;
  event.currentTarget.querySelectorAll<HTMLElement>("[data-ch]").forEach((letter) => {
    const box = letter.getBoundingClientRect();
    const distance = Math.abs(x - (box.left + box.width / 2));
    const k = Math.max(0, 1 - distance / (box.width * 1.6));
    letter.style.transform = `translateY(${-k * 10}%)`;
    letter.style.color = k > 0.45 ? "var(--acc)" : "";
  });
}

function wordmarkLeave(event: MouseEvent<HTMLDivElement>) {
  event.currentTarget.querySelectorAll<HTMLElement>("[data-ch]").forEach((letter) => {
    letter.style.transform = "";
    letter.style.color = "";
  });
}

export function SiteFooter() {
  const pathname = usePathname();
  const router = useRouter();
  return (
    <footer data-reveal="" data-self="0" className="fu-footer">
      <div
        aria-hidden
        className="absolute bottom-[-30%] left-1/2 -z-10 aspect-[2/1] w-4/5 -translate-x-1/2 rounded-[50%] blur-[30px]"
        style={{ background: "radial-gradient(ellipse, rgba(198,255,61,.10), transparent 65%)" }}
      />
      <div className="fu-grid items-start" style={grid("380px", "clamp(40px,6cqi,80px)")}>
        <div data-stagger="" className="flex flex-col gap-6">
          <Link href="/" aria-label="First User home" className="flex items-center gap-2.5 self-start">
            <span className="fu-logo-mark">
              <span />
            </span>
            <span className="fu-logo-word">First User</span>
          </Link>
          <p className="fu-display text-footer" style={{ lineHeight: 0.9 }}>
            Your first user.
            <br />
            <span className="text-ink4">Before the real ones.</span>
          </p>
          <div className="flex flex-wrap gap-2.5">
            <a
              href={`/#${FORM_ANCHOR}`}
              className="fu-btn fu-btn-md fu-btn-with-arrow"
              style={{ paddingLeft: 20 }}
              onClick={(event) => goToForm(event, pathname, router.push)}
            >
              Test my website
              <span aria-hidden className="fu-arrow" style={{ width: 36, height: 36 }}>
                →
              </span>
            </a>
            <Link href="/journey" className="fu-btn fu-btn-md fu-btn-outline gap-2" style={{ paddingInline: 20 }}>
              <span aria-hidden className="fu-dot-live" />
              Building in public →
            </Link>
          </div>
        </div>
        <div data-stagger="" className="fu-grid" style={grid("150px", "28px")}>
          <div className="flex flex-col gap-3">
            <span className="fu-eyebrow mb-1 text-ink4">Pages</span>
            {NAV_ITEMS.map((item) => (
              <Link key={item.label} href={item.href} className="fu-footer-link">
                {item.label}
              </Link>
            ))}
          </div>
          <div className="flex flex-col gap-3">
            <span className="fu-eyebrow mb-1 text-ink4">Elsewhere</span>
            <a href={SOCIAL.x.href} target="_blank" rel="noopener noreferrer" className="fu-footer-link">
              X · {SOCIAL.x.handle} <span className="text-[13px]">↗</span>
            </a>
            <a href={SOCIAL.linkedin.href} target="_blank" rel="noopener noreferrer" className="fu-footer-link">
              LinkedIn <span className="text-[13px]">↗</span>
            </a>
            <a href={SOCIAL.repo.href} target="_blank" rel="noopener noreferrer" className="fu-footer-link">
              GitHub <span className="text-[13px]">↗</span>
            </a>
          </div>
          <div className="flex flex-col gap-3">
            <span className="fu-eyebrow mb-1 text-ink4">Built with</span>
            <span className="text-[16px] leading-[1.6] text-ink2">
              #neatHack
              <br />
              neatlogs
              <br />
              Entire
              <br />
              cfo.ai
            </span>
          </div>
        </div>
      </div>
      <div className="mt-[clamp(48px,6cqi,72px)] flex flex-wrap items-center justify-between gap-3 border-t border-line py-[18px]">
        <span className="font-code text-[13px] text-ink3">Built solo by Divyanshu Verma · 2026</span>
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" })}
          className="fu-btn fu-btn-ghost h-10 px-4 font-code text-[13px] hover:-translate-y-[3px]"
        >
          ↑ Back to top
        </button>
      </div>
      <div aria-hidden className="fu-wordmark" onMouseMove={wordmarkMove} onMouseLeave={wordmarkLeave}>
        {WORDMARK.map((letter, index) => (
          <span
            key={index}
            data-stagger="translateY(40%)"
            data-ch=""
            style={letter === " " ? { width: ".22em" } : undefined}
          >
            {letter === " " ? " " : letter}
          </span>
        ))}
      </div>
    </footer>
  );
}
