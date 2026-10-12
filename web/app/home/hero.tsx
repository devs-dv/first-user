"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, type FormEvent, type MouseEvent } from "react";

import { grid } from "@/lib/css";
import { EXAMPLE_SITE } from "@/lib/site";

import { reducedMotion } from "../motion";
import { goToForm } from "../site-header";
import { HERO_RUN, MARQUEE, PHASES } from "./data";
import { setHome, useHeroClock, useHome } from "./store";
import { urlFieldHandlers } from "./url-field";

const RESULT = {
  ok: { label: "Done", bg: "var(--green-soft)", fg: "var(--green-ink)" },
  retry: { label: "Needed a retry", bg: "var(--amber-soft)", fg: "var(--amber-ink)" },
  done: { label: "Report ready", bg: "var(--acc)", fg: "var(--on-acc)" },
};

export function Hero() {
  useHeroClock();
  const step = useHome((s) => s.step);
  const url = useHome((s) => s.url);
  const pathname = usePathname();
  const router = useRouter();
  const cardRef = useRef<HTMLDivElement>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const firstStep = useRef(true);

  const h = HERO_RUN[step];
  const result = RESULT[h.res];
  const verified = step >= 6;
  const cursorY = h.rows.length > 1 ? 56 : 41;

  // The step card under the demo nudges up each time the run moves on.
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    const feed = feedRef.current;
    if (feed?.animate && !reducedMotion()) {
      feed.animate([{ transform: "translateY(10px)", opacity: 0.3 }, { transform: "none", opacity: 1 }], {
        duration: 450,
        easing: "cubic-bezier(.2,.8,.2,1)",
      });
    }
  }, [step]);

  function heroMove(event: MouseEvent<HTMLElement>) {
    if (reducedMotion()) return;
    const el = event.currentTarget;
    const box = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${(((event.clientX - box.left) / box.width) * 100).toFixed(1)}%`);
    el.style.setProperty("--my", `${(((event.clientY - box.top) / box.height) * 100).toFixed(1)}%`);
  }

  function tilt(event: MouseEvent<HTMLDivElement>) {
    const card = cardRef.current;
    if (!card || reducedMotion()) return;
    const box = card.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    card.style.transform = `rotateY(${x * 6}deg) rotateX(${-y * 6}deg)`;
  }

  function go(event: FormEvent | MouseEvent) {
    setHome({ tab: "test" });
    goToForm(event as MouseEvent, pathname, router.push);
  }

  return (
    <>
      <section data-screen-label="Home" onMouseMove={heroMove} className="relative isolate">
        <div
          aria-hidden
          className="fu-dots inset-0 opacity-95"
          style={{
            WebkitMaskImage: "radial-gradient(ellipse 55% 65% at var(--mx,70%) var(--my,45%), #000 15%, transparent 72%)",
            maskImage: "radial-gradient(ellipse 55% 65% at var(--mx,70%) var(--my,45%), #000 15%, transparent 72%)",
          }}
        />
        <div
          aria-hidden
          className="absolute -z-10 rounded-full blur-[34px]"
          style={{
            left: "calc(var(--mx,72%) - min(240px,45cqi))",
            top: "calc(var(--my,40%) - min(240px,45cqi))",
            width: "min(480px,90cqi)",
            height: "min(480px,90cqi)",
            background: "radial-gradient(circle, color-mix(in srgb, var(--acc) 40%, transparent), transparent 65%)",
            transition: "left 1.2s var(--e-out), top 1.2s var(--e-out)",
          }}
        />
        <div
          className="fu-grid items-center"
          style={grid("460px", "64px", { padding: "48px var(--gutter) 104px" })}
        >
          <div className="flex flex-col gap-7">
            <span className="fu-pill-tag">
              <span className="fu-dot-live" />
              Built at #neatHack
            </span>
            <h1 className="fu-display flex flex-col text-hero" style={{ lineHeight: 0.86, letterSpacing: "-.01em" }}>
              <span className="fu-line" style={{ paddingBottom: ".04em" }}>
                <span>Your first user.</span>
              </span>
              <span className="fu-line" style={{ padding: ".06em 0" }}>
                <span>
                  <span className="fu-mark" style={{ marginLeft: -4 }}>
                    Before
                  </span>{" "}
                  the
                </span>
              </span>
              <span className="fu-line" style={{ paddingBottom: ".04em" }}>
                <span>real ones.</span>
              </span>
            </h1>
            <p className="m-0 max-w-[500px] text-lede font-medium leading-[1.4] text-ink fu-pretty">
              Find out whether a stranger can actually use your product, before you spend money acquiring users.
            </p>
            <form
              onSubmit={(event) => go(event)}
              className="flex max-w-[540px] items-center gap-2 rounded-pill border-[1.5px] border-ink bg-s1 py-2 pl-[18px] pr-2 shadow-press"
            >
              <span aria-hidden className="font-code text-[15px] font-medium text-ink4">
                https://
              </span>
              <label htmlFor="hero-url" className="sr-only">
                Your website&apos;s address
              </label>
              <input
                id="hero-url"
                value={url}
                onChange={(event) => setHome({ url: event.target.value })}
                {...urlFieldHandlers((value) => setHome({ url: value }))}
                placeholder="your-app.com"
                inputMode="url"
                autoComplete="url"
                className="min-w-0 flex-1 border-none bg-transparent font-code text-[16px] font-medium text-ink outline-none"
              />
              <button
                type="submit"
                className="h-12 cursor-pointer whitespace-nowrap rounded-pill border-none bg-acc px-5 text-[15px] font-semibold text-on-acc transition-colors hover:bg-acc-h"
              >
                Test<span className="fu-cta-text"> my website</span> →
              </button>
            </form>
            <p className="-mt-3 ml-[18px] max-w-[480px] text-[15px] leading-normal text-ink3">
              Pick a goal next. First User opens your site and attempts it in a real browser.
            </p>
            <div className="flex flex-wrap items-center gap-x-[18px] gap-y-2.5 font-code text-[13px] font-medium text-ink3">
              <button
                type="button"
                onClick={() => setHome({ url: EXAMPLE_SITE })}
                className="h-8 cursor-pointer whitespace-nowrap rounded-pill border border-dashed border-ink3 bg-transparent px-3 font-code text-[13px] font-medium text-ink hover:border-solid hover:bg-s1"
              >
                Try {EXAMPLE_SITE}
              </button>
              <span className="flex flex-wrap items-center gap-x-[18px] gap-y-2">
                <span>A few minutes</span>
                <span aria-hidden className="size-1 rounded-full bg-ink4" />
                <span>Real browser</span>
                <span aria-hidden className="size-1 rounded-full bg-ink4" />
                <span>Watch it live</span>
              </span>
            </div>
          </div>

          <div
            onMouseMove={tilt}
            onMouseLeave={() => {
              if (cardRef.current) cardRef.current.style.transform = "";
            }}
            className="relative pb-9"
            style={{ perspective: 1200 }}
            role="img"
            aria-label="Demo: a first-time visitor creating a project on a made-up site, step by step, until the goal is reached and verified."
          >
            <div
              aria-hidden
              className="absolute -right-2 -top-[22px] z-[4] flex h-10 items-center gap-2 whitespace-nowrap rounded-pill border-[1.5px] border-ink-fixed bg-acc pl-2 pr-3.5 text-[14px] font-semibold text-on-acc"
              style={{
                boxShadow: "var(--sh-badge)",
                opacity: verified ? 1 : 0,
                transform: verified ? "none" : "translateY(8px) scale(.9)",
                transition: "opacity .4s, transform .5s var(--e-pop)",
              }}
            >
              <span className="flex size-6 items-center justify-center rounded-full bg-ink-fixed text-[13px] text-acc-fixed">
                ✓
              </span>
              Goal reached · verified
            </div>
            <div aria-hidden ref={cardRef} style={{ transition: "transform .25s ease-out", transformStyle: "preserve-3d" }}>
              <div className="overflow-hidden rounded-cardsm border-[1.5px] border-ink bg-s1 shadow-hard-xl">
                <div className="flex items-center gap-2.5 border-b border-line bg-s2 px-4 py-3">
                  <span className="fu-traffic">
                    <span />
                    <span />
                    <span />
                  </span>
                  <span className="flex h-7 min-w-0 flex-1 items-center overflow-hidden whitespace-nowrap rounded-r8 border border-line bg-s1 px-3 font-code text-[12px] font-medium text-ink3">
                    taskpond.app{h.path}
                  </span>
                  <span className="flex h-[26px] items-center gap-1.5 whitespace-nowrap rounded-pill bg-ink-fixed px-2.5 font-code text-[11px] font-medium text-acc-fixed">
                    <span className="size-1.5 rounded-full bg-acc-fixed" style={{ animation: "fuBlink 1s infinite" }} />
                    LIVE · {step + 1}
                  </span>
                </div>
                <div
                  className="relative grid h-[300px] overflow-hidden bg-page text-page-ink"
                  style={{ gridTemplateColumns: "minmax(70px,22%) minmax(0,1fr)" }}
                >
                  <div className="flex flex-col gap-2.5 border-r border-page-line bg-page-side px-3 py-4">
                    <span className="text-[13px] font-bold">Taskpond</span>
                    <span className="h-2 w-[70%] rounded bg-page-line" />
                    <span className="h-2 w-[55%] rounded bg-page-line" />
                    <span className="h-2 w-[62%] rounded bg-page-line" />
                  </div>
                  <div className="flex min-w-0 flex-col gap-3 p-[18px]">
                    <span className="h-[30px] overflow-hidden text-[20px] font-semibold leading-[1.2]">{h.title}</span>
                    {h.rows.map((row, index) => (
                      <span
                        key={index}
                        className="flex h-[34px] items-center overflow-hidden whitespace-nowrap rounded-r8 border border-page-line px-2.5 text-[13px] text-page-ink2"
                      >
                        {row}
                      </span>
                    ))}
                    <span
                      className="flex h-[34px] items-center self-start whitespace-nowrap rounded-r8 bg-page-btn px-3.5 text-[13px] font-medium text-white"
                      style={{
                        outline: `2.5px solid ${h.res === "retry" ? "#A86400" : "#0E1320"}`,
                        outlineOffset: 3,
                        transition: "outline-color .3s",
                      }}
                    >
                      {h.target}
                    </span>
                  </div>
                  <div
                    className="pointer-events-none absolute z-[2]"
                    style={{
                      left: "30%",
                      top: `${cursorY}%`,
                      transition: "left 1.1s var(--e-cursor), top 1.1s var(--e-cursor)",
                    }}
                  >
                    <svg width="22" height="22" viewBox="0 0 22 22" className="block" style={{ filter: "drop-shadow(0 2px 3px rgba(0,0,0,.25))" }}>
                      <path d="M2 2l7 18 2.6-7.4L19 10z" fill="#0E1320" stroke="#FFFFFF" strokeWidth="1.5" strokeLinejoin="round" />
                    </svg>
                    <div
                      className="absolute left-5 top-[18px] rounded-[12px_12px_12px_4px] bg-ink-fixed px-3 py-2.5 text-[13px] leading-[1.4] text-white"
                      style={{ width: "min(230px,52cqi)", boxShadow: "0 10px 24px rgba(14,19,32,.25)" }}
                    >
                      <span className="mb-[3px] block font-code text-[10px] font-medium tracking-[.06em] text-acc-fixed">
                        THINKING
                      </span>
                      {h.thought}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-4 border-t border-line">
                  {PHASES.map((name, i) => {
                    const done = i < h.ph || h.res === "done";
                    const on = i === h.ph && !done;
                    return (
                      <div
                        key={name}
                        className="flex flex-col items-center gap-[7px] px-1.5 pb-3.5 pt-3 text-center"
                        style={{ background: on ? "var(--acc-soft)" : "var(--s1)", transition: "background .4s" }}
                      >
                        <span
                          className="flex size-5 items-center justify-center rounded-full text-[11px] font-semibold"
                          style={{
                            border: `1.5px solid ${done || on ? "var(--ink)" : "var(--off)"}`,
                            background: done ? "var(--acc)" : "var(--s1)",
                            color: done ? "#0E1320" : "var(--ink)",
                            transition: "all .4s",
                          }}
                        >
                          {done ? "✓" : i + 1}
                        </span>
                        <span className="text-[12px] font-medium leading-[1.25]" style={{ color: done || on ? "var(--ink)" : "var(--ink4)" }}>
                          {name}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div
              aria-hidden
              ref={feedRef}
              className="absolute -left-3 bottom-0 z-[3] flex w-[min(300px,80%)] flex-col gap-1.5 rounded-frame border-[1.5px] border-ink bg-s1 px-4 py-3.5 shadow-float"
            >
              <div className="flex items-center justify-between">
                <span className="font-code text-[11px] font-medium tracking-[.05em] text-ink3">DEMO · STEP {step + 1}</span>
                <span
                  className="flex h-[22px] items-center whitespace-nowrap rounded-pill px-[9px] text-[11px] font-semibold"
                  style={{ background: result.bg, color: result.fg }}
                >
                  {result.label}
                </span>
              </div>
              <div className="font-code text-[14px] font-medium text-ink">{h.act}</div>
            </div>
          </div>
        </div>
      </section>

      <div
        aria-hidden
        className="relative z-[2] overflow-hidden border-y-[1.5px] border-ink bg-[#0E1116] text-[#F1F2F4]"
        style={{ transform: "rotate(-1.2deg)", margin: "-10px -12px -6px" }}
      >
        <div className="flex w-max" style={{ animation: "fuMarq var(--marquee) linear infinite" }}>
          {[...MARQUEE, ...MARQUEE].map((item, index) => (
            <span
              key={index}
              className="flex items-center gap-[26px] whitespace-nowrap px-[13px] py-4 font-display text-[24px] font-[850] uppercase tracking-[.01em]"
              style={{ fontStretch: "72%" }}
            >
              {item}
              <span className="text-[18px] text-acc-fixed">✦</span>
            </span>
          ))}
        </div>
      </div>
    </>
  );
}
