"use client";

// "The whole run": every step as a card with its screenshot, what the visitor did, its own reason and what happened.
// On wider screens a snapping carousel with previous/next, a counter and a progress line; on a phone a vertical
// timeline. Screenshots open full size in a lightbox. Each card is the target of the report's "step N" links.

import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import {
  describeAction,
  isHttpUrl,
  pathOf,
  stepKind,
  stepMarks,
  stepStatus,
  type StepKind,
  type StepMark,
  type StepTone,
} from "@/lib/report-view";
import type { Step } from "@/lib/types";

import { reducedMotion } from "../../motion";

const TONE: Record<StepTone, { bg: string; fg: string }> = {
  done: { bg: "var(--green-soft)", fg: "var(--green-ink)" },
  retry: { bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  error: { bg: "var(--bad-soft)", fg: "var(--bad-ink)" },
  problem: { bg: "var(--bad)", fg: "var(--on-bad)" },
  ours: { bg: "var(--s2)", fg: "var(--ink2)" },
  end: { bg: "var(--acc)", fg: "var(--on-acc)" },
  blocked: { bg: "var(--blue-soft)", fg: "var(--blue-ink)" },
};

// The accent of a step that matters, strongest first.
const MARK_COLOR: Record<StepMark, string> = {
  Finding: "var(--bad)",
  "Page error": "var(--bad)",
  Recovery: "var(--warn)",
  "Final step": "var(--ink)",
};

const KIND_LABEL: Record<StepKind, string> = {
  look: "Look",
  click: "Click",
  type: "Type",
  scroll: "Scroll",
  back: "Back",
  note: "Note",
  finish: "Finish",
  login: "Sign in",
};

// Small line icons, drawn in the current text colour.
function KindIcon({ kind }: { kind: StepKind }) {
  const paths: Record<StepKind, ReactNode> = {
    look: (
      <>
        <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z" />
        <circle cx="8" cy="8" r="2" />
      </>
    ),
    click: <path d="M4 2.5l8 4-3.4 1.2L7.2 11 4 2.5Zm4.6 5.2L12 11" />,
    type: (
      <>
        <rect x="1.5" y="4" width="13" height="8" rx="1.5" />
        <path d="M4 7h1M7 7h1M10 7h2M4.5 9.5h7" />
      </>
    ),
    scroll: <path d="M8 2v12M5 5l3-3 3 3M5 11l3 3 3-3" />,
    back: <path d="M6 4L2 8l4 4M2 8h12" />,
    note: <path d="M3 2.5h7l3 3v8H3v-11ZM5.5 7h5M5.5 9.5h5" />,
    finish: <path d="M3.5 14V2.5M3.5 3h8l-1.5 2.5L11.5 8h-8" />,
    login: (
      <>
        <rect x="3" y="7" width="10" height="7" rx="1.5" />
        <path d="M5.5 7V5a2.5 2.5 0 015 0v2" />
      </>
    ),
  };
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {paths[kind]}
    </svg>
  );
}

// What happened, in words, under the coloured result.
const RETRY_WORDING: Record<string, string> = {
  b: "Worked on the second try, after our browser tool looked for the element again.",
  c: "Worked on the third try, with a direct click on the element.",
  d: "Worked on the fourth try, with a real mouse click.",
};

// The worker caps summaries at this length; older runs cut them mid-word.
const SUMMARY_LIMIT = 400;

function tidySummary(summary: string): string {
  const trimmed = summary.trim();
  if (summary.length < SUMMARY_LIMIT || /[.!?…)"']$/.test(trimmed)) return trimmed;
  const lastSpace = trimmed.lastIndexOf(" ");
  const cut = lastSpace > SUMMARY_LIMIT / 2 ? trimmed.slice(0, lastSpace) : trimmed;
  return `${cut.replace(/[\s,;:-]+$/, "")}…`;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function describeResult(step: Step): string | null {
  const result = step.result ?? {};
  const input = step.input ?? {};
  if (result.error) return "The browser tool hit an error on this step.";
  switch (step.tool) {
    case "look":
      return result.unchanged ? "Nothing had changed since the last look." : tidySummary(text(result.summary)) || null;
    case "do":
      if (result.success) return RETRY_WORDING[text(result.rung)] ?? null;
      return "Nothing happened. Our browser tool may have failed here, so this is logged as our issue.";
    case "note_friction":
      return `Expected: ${text(input.expected)} What happened: ${text(input.happened)}`;
    case "finish":
      return text(input.reason) || null;
    default:
      return null;
  }
}

// ------------------------------------------------------------------------------------- lightbox

function Lightbox({ shots, index, onClose, onMove }: { shots: Step[]; index: number; onClose: () => void; onMove: (to: number) => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const step = shots[index];

  useEffect(() => {
    closeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowRight" && index < shots.length - 1) onMove(index + 1);
      else if (event.key === "ArrowLeft" && index > 0) onMove(index - 1);
      else if (event.key === "Tab") {
        // Keep focus inside the dialog.
        const focusable = [...document.querySelectorAll<HTMLElement>("#fu-lightbox button:not([disabled])")];
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [index, shots.length, onClose, onMove]);

  return (
    <div
      id="fu-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={`Screenshot of step ${step.idx}`}
      className="fixed inset-0 z-[90] flex flex-col bg-[rgba(7,8,10,.92)] p-3 text-night-ink sm:p-6"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex items-center justify-between gap-3 pb-3">
        <span className="min-w-0 truncate text-[15px] font-medium">
          <span className="font-code text-[12px] text-night-ink3">
            Step {step.idx} · {index + 1} of {shots.length} ·{" "}
          </span>
          {describeAction(step)}
        </span>
        <button ref={closeRef} type="button" onClick={onClose} className="fu-btn fu-btn-ghost h-10 flex-none border-night-ink bg-night-s1 text-night-ink hover:bg-night-s1 hover:text-night-ink">
          Close ✕
        </button>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center" onClick={(event) => event.target === event.currentTarget && onClose()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={step.screenshot_path as string} alt={`The page after step ${step.idx}`} className="max-h-full max-w-full rounded-field border border-night-line2 bg-white object-contain" />
      </div>
      <div className="flex items-center justify-between gap-3 pt-3">
        <button type="button" disabled={index === 0} onClick={() => onMove(index - 1)} className="fu-btn fu-btn-ghost h-10 border-night-ink bg-night-s1 text-night-ink hover:bg-night-s1 hover:text-night-ink disabled:opacity-40">
          ← Previous
        </button>
        <span className="hidden font-code text-[12px] text-night-ink3 sm:inline">Esc to close · ← → to move</span>
        <button type="button" disabled={index === shots.length - 1} onClick={() => onMove(index + 1)} className="fu-btn fu-btn-ghost h-10 border-night-ink bg-night-s1 text-night-ink hover:bg-night-s1 hover:text-night-ink disabled:opacity-40">
          Next →
        </button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------- the strip

export function StepsStrip({ steps, highlight, live = false }: { steps: Step[]; highlight: Set<number>; live?: boolean }) {
  const listRef = useRef<HTMLOListElement>(null);
  const [position, setPosition] = useState(0);
  const [lightbox, setLightbox] = useState<number | null>(null);
  const shots = steps.filter((step) => isHttpUrl(step.screenshot_path));
  const lastIdx = steps.length ? steps[steps.length - 1].idx : -1;
  // Closing returns focus to the thumbnail of the step last shown, so keyboard users land where they were.
  const closeLightbox = useCallback(() => {
    setLightbox((open) => {
      const idx = open !== null ? shots[open]?.idx : undefined;
      if (idx !== undefined) {
        requestAnimationFrame(() => document.querySelector<HTMLElement>(`#step-${idx} button`)?.focus({ preventScroll: true }));
      }
      return null;
    });
  }, [shots]);

  // Where the carousel is: the share of the way scrolled, as a step. Vertical (phone) layout has no sideways scroll.
  const onScroll = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    const room = list.scrollWidth - list.clientWidth;
    setPosition(room > 0 ? Math.round((list.scrollLeft / room) * (steps.length - 1)) : 0);
  }, [steps.length]);

  // Cards ease in as they come into view (in either direction). Without motion they are simply there.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const cards = [...list.querySelectorAll<HTMLElement>(".fu-step")];
    if (reducedMotion() || typeof IntersectionObserver === "undefined") {
      cards.forEach((card) => card.classList.add("is-in"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.15 },
    );
    cards.forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, [steps.length]);

  function move(by: number) {
    const list = listRef.current;
    const card = list?.querySelector<HTMLElement>(".fu-step");
    if (!list || !card) return;
    list.scrollBy({ left: by * (card.offsetWidth + 16), behavior: reducedMotion() ? "auto" : "smooth" });
  }

  const current = steps[Math.min(position, steps.length - 1)];

  return (
    <section id="fu-r-steps" aria-labelledby="steps-title" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2.5">
        <div className="flex flex-col gap-2.5">
          <span className="fu-eyebrow">{live ? "Steps so far" : "03 · Every step"}</span>
          <h2 id="steps-title" className="fu-display fu-display-mid text-block" style={{ lineHeight: 0.95 }}>
            The whole run
          </h2>
        </div>
        {steps.length > 1 && (
          <div className="fu-steps-controls items-center gap-2">
            <button type="button" onClick={() => move(-1)} disabled={position === 0} aria-label="Previous steps" className="fu-icon-btn size-10 border-ink disabled:opacity-40 hover:rotate-0">
              ←
            </button>
            <span className="min-w-[110px] text-center font-code text-[13px] font-medium" aria-live="polite">
              Step {current?.idx ?? 1} of {steps.length}
            </span>
            <button type="button" onClick={() => move(1)} disabled={position >= steps.length - 1} aria-label="Next steps" className="fu-icon-btn size-10 border-ink disabled:opacity-40 hover:rotate-0">
              →
            </button>
          </div>
        )}
      </div>
      {steps.length > 1 && (
        <div aria-hidden className="fu-steps-controls h-[3px] overflow-hidden rounded-[3px] bg-line">
          <span
            className="block h-full origin-left bg-acc"
            style={{ transform: `scaleX(${(position + 1) / steps.length})`, transition: "transform .3s var(--e-out)", width: "100%" }}
          />
        </div>
      )}
      {steps.length === 0 ? (
        <p className="m-0 text-[15px] text-ink2">No steps were recorded.</p>
      ) : (
        <ol ref={listRef} onScroll={onScroll} className="fu-steps" tabIndex={0} aria-label="Steps of the visit">
          {steps.map((step) => {
            const status = stepStatus(step);
            const tone = TONE[status.tone];
            const marks = stepMarks(step, highlight, lastIdx);
            const accent = marks.length ? MARK_COLOR[marks[0]] : null;
            const kind = stepKind(step);
            const result = describeResult(step);
            const shotIndex = shots.findIndex((shot) => shot.idx === step.idx);
            return (
              <li
                key={step.idx}
                id={`step-${step.idx}`}
                className="fu-step scroll-mt-28"
                style={accent ? ({ "--step-accent": accent } as CSSProperties) : undefined}
              >
                <div
                  className="flex h-full flex-col overflow-hidden rounded-card bg-s1"
                  style={{ border: `${accent ? 2 : 1.5}px solid ${accent ?? "var(--line)"}` }}
                >
                  {shotIndex >= 0 ? (
                    <button
                      type="button"
                      onClick={() => setLightbox(shotIndex)}
                      aria-label={`Open the screenshot of step ${step.idx} full size`}
                      className="group relative block cursor-zoom-in border-b border-line bg-page p-0"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={step.screenshot_path as string}
                        alt={`The page after step ${step.idx}`}
                        loading="lazy"
                        className="block aspect-[16/10] w-full object-cover object-top"
                      />
                      <span aria-hidden className="absolute bottom-2 right-2 rounded-pill bg-ink-fixed/85 px-2.5 py-1 font-code text-[11px] text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                        View full size
                      </span>
                    </button>
                  ) : (
                    <div className="flex items-center justify-between gap-2 border-b border-line bg-s2 px-4 py-3 font-code text-[11px] text-ink4">
                      <span className="truncate">{pathOf(step.url) || "/"}</span>
                      <span className="flex-none">No screenshot for this step</span>
                    </div>
                  )}
                  <div className="flex flex-1 flex-col gap-2.5 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-code text-[12px] font-medium text-ink3">Step {step.idx}</span>
                      <span className="flex h-6 items-center gap-1.5 rounded-pill border border-line px-2 font-code text-[11px] font-medium text-ink2">
                        <KindIcon kind={kind} />
                        {KIND_LABEL[kind]}
                      </span>
                      {marks.length > 0 && (
                        <span className="ml-auto flex flex-wrap gap-1">
                          {marks.map((mark) => (
                            <span
                              key={mark}
                              className="flex h-6 items-center rounded-pill px-2 font-code text-[11px] font-medium uppercase tracking-[.04em]"
                              style={{ background: MARK_COLOR[mark], color: mark === "Recovery" ? "#0E1320" : "var(--bg)" }}
                            >
                              {mark}
                            </span>
                          ))}
                        </span>
                      )}
                    </div>
                    <span className="text-[17px] font-semibold leading-[1.35] [overflow-wrap:anywhere]">{describeAction(step)}</span>
                    {step.thought && (
                      <span className="line-clamp-3 text-[14px] leading-[1.45] text-ink3" title={step.thought}>
                        {step.thought}
                      </span>
                    )}
                    <div className="mt-auto flex flex-col gap-1.5 pt-1">
                      <span
                        className="flex h-[26px] items-center self-start whitespace-nowrap rounded-pill px-2.5 text-[12px] font-semibold"
                        style={{ background: tone.bg, color: tone.fg }}
                      >
                        {status.label}
                      </span>
                      {result && (
                        <span className="line-clamp-3 text-[13px] leading-[1.45] text-ink2" title={result}>
                          {result}
                        </span>
                      )}
                      {step.url && <span className="truncate font-code text-[11px] text-ink4">{pathOf(step.url) || "/"}</span>}
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {lightbox !== null && shots[lightbox] && <Lightbox shots={shots} index={lightbox} onClose={closeLightbox} onMove={setLightbox} />}
    </section>
  );
}
