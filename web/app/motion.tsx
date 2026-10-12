"use client";

// The page motion from the design, in one place: heading lines that slide up, sections that fade in as
// they scroll into view (with their [data-stagger], [data-pop] and [data-line] children), counters
// ([data-count]) and scroll-linked bars ([data-scrub], [data-scrub-y], [data-mdot]).
//
// Pages only mark elements with data attributes. Content that arrives later (a report fetched in the
// browser) is picked up by a MutationObserver. With prefers-reduced-motion nothing moves: everything is
// shown in its final state and the bars are full.

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const EASE = "cubic-bezier(.16,1,.3,1)";
const KIDS = "[data-stagger],[data-pop],[data-line]";

// React marks a DOM node once it owns it. Until a streamed part of the page has hydrated, its HTML must stay
// exactly as the server sent it, or React reports a mismatch; such parts are scanned again shortly after.
function hydrated(el: Element): boolean {
  return Object.keys(el).some((key) => key.startsWith("__reactFiber$"));
}

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function countUp(el: HTMLElement) {
  const to = Number(el.dataset.count);
  const from = el.dataset.from != null ? Number(el.dataset.from) : 0;
  const suffix = el.dataset.suf ?? "";
  if (!Number.isFinite(to) || !Number.isFinite(from)) return;
  const start = performance.now();
  const duration = 1200;
  const tick = (now: number) => {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(from + (to - from) * eased) + suffix;
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function scrub() {
  const vh = window.innerHeight;
  document.querySelectorAll<HTMLElement>("[data-scrub-y]").forEach((el) => {
    const box = el.getBoundingClientRect();
    const p = Math.min(1, Math.max(0, (vh * 0.6 - box.top) / Math.max(1, box.height)));
    const fill = el.firstElementChild as HTMLElement | null;
    if (fill) fill.style.transform = `scaleY(${p})`;
  });
  document.querySelectorAll<HTMLElement>("[data-mdot]").forEach((dot) => {
    const on = dot.getBoundingClientRect().top < vh * 0.6;
    dot.style.background = on ? "var(--acc)" : "";
    dot.style.transform = on ? "scale(1.15)" : "";
  });
  document.querySelectorAll<HTMLElement>("[data-scrub]").forEach((el) => {
    const box = el.getBoundingClientRect();
    const p = Math.min(1, Math.max(0, (vh * 0.9 - box.top) / (vh * 0.55)));
    const fill = el.firstElementChild as HTMLElement | null;
    if (fill) fill.style.transform = `scaleX(${p})`;
  });
}

function showEverything() {
  document.querySelectorAll<HTMLElement>("[data-scrub] > span").forEach((fill) => (fill.style.transform = "none"));
  document.querySelectorAll<HTMLElement>("[data-scrub-y] > span").forEach((fill) => (fill.style.transform = "none"));
  document.querySelectorAll<HTMLElement>("[data-mdot]").forEach((dot) => (dot.style.background = "var(--acc)"));
  document.querySelectorAll<HTMLElement>(KIDS).forEach((el) => (el.style.opacity = ""));
}

// Anything still hidden that is on screen is shown: a missed intersection never leaves a blank section.
function revealVisibleLeftovers() {
  document.querySelectorAll<HTMLElement>(KIDS).forEach((el) => {
    const box = el.getBoundingClientRect();
    if (el.style.opacity === "0" && box.top < window.innerHeight && box.bottom > 0) el.style.opacity = "";
  });
}

export function MotionRuntime() {
  const pathname = usePathname();

  useEffect(() => {
    if (reducedMotion() || typeof IntersectionObserver === "undefined") {
      showEverything();
      const observer = new MutationObserver(() => showEverything());
      observer.observe(document.body, { childList: true, subtree: true });
      return () => observer.disconnect();
    }

    const seen = new WeakSet<Element>();
    const linesSeen = new WeakSet<Element>();

    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target as HTMLElement;
          io.unobserve(el);
          if (el.dataset.self !== "0") {
            el.animate([{ opacity: 0, transform: "translateY(28px)" }, { opacity: 1, transform: "none" }], {
              duration: 800,
              easing: EASE,
            });
          }
          el.querySelectorAll<HTMLElement>("[data-stagger]").forEach((child, i) => {
            child.animate(
              [{ opacity: 0, transform: child.dataset.stagger || "translateY(32px)" }, { opacity: 1, transform: "none" }],
              { duration: 900, delay: 80 + i * 90, easing: EASE, fill: "backwards" },
            );
            child.style.opacity = "";
          });
          el.querySelectorAll<HTMLElement>("[data-pop]").forEach((child, i) => {
            child.animate([{ opacity: 0, transform: "scale(.4)" }, { opacity: 1, transform: "none" }], {
              duration: 500,
              delay: 500 + i * 60,
              easing: "cubic-bezier(.3,1.6,.5,1)",
              fill: "backwards",
            });
            child.style.opacity = "";
          });
          el.querySelectorAll<HTMLElement>("[data-line]").forEach((child, i) => {
            child.animate([{ opacity: 0, transform: "translateX(-8px)" }, { opacity: 1, transform: "none" }], {
              duration: 600,
              delay: 700 + i * 260,
              easing: EASE,
              fill: "backwards",
            });
            child.style.opacity = "";
          });
          el.querySelectorAll<HTMLElement>("[data-count]").forEach(countUp);
        }),
      { rootMargin: "0px 0px -12% 0px" },
    );

    let safety: ReturnType<typeof setTimeout> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;

    function scan() {
      let waiting = false;
      let lineIndex = 0;
      document.querySelectorAll<HTMLElement>(".fu-line > span").forEach((line) => {
        if (linesSeen.has(line)) return;
        if (!hydrated(line)) {
          waiting = true;
          return;
        }
        linesSeen.add(line);
        line.animate([{ transform: "translateY(105%)" }, { transform: "none" }], {
          duration: 900,
          delay: 120 + lineIndex++ * 90,
          easing: EASE,
          fill: "backwards",
        });
      });
      document.querySelectorAll<HTMLElement>("[data-reveal]").forEach((el) => {
        if (seen.has(el)) return;
        if (!hydrated(el)) {
          waiting = true;
          return;
        }
        seen.add(el);
        const kids = el.querySelectorAll<HTMLElement>(KIDS);
        const box = el.getBoundingClientRect();
        if (box.top < window.innerHeight && box.bottom > 0) {
          kids.forEach((child) => (child.style.opacity = ""));
          el.querySelectorAll<HTMLElement>("[data-count]").forEach(countUp);
          return;
        }
        kids.forEach((child) => (child.style.opacity = "0"));
        io.observe(el);
      });
      scrub();
      clearTimeout(safety);
      safety = setTimeout(revealVisibleLeftovers, 1500);
      clearTimeout(retry);
      if (waiting) retry = setTimeout(scan, 150);
    }

    let frame = 0;
    let settle: ReturnType<typeof setTimeout> | undefined;
    const onScroll = () => {
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          scrub();
        });
      }
      clearTimeout(settle);
      settle = setTimeout(revealVisibleLeftovers, 1200);
    };

    let pending: ReturnType<typeof setTimeout> | undefined;
    const mutations = new MutationObserver(() => {
      clearTimeout(pending);
      pending = setTimeout(scan, 60);
    });

    scan();
    mutations.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      io.disconnect();
      mutations.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      clearTimeout(safety);
      clearTimeout(retry);
      clearTimeout(settle);
      clearTimeout(pending);
      cancelAnimationFrame(frame);
      document.querySelectorAll<HTMLElement>(KIDS).forEach((child) => (child.style.opacity = ""));
    };
  }, [pathname]);

  return null;
}
