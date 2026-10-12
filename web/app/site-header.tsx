"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type MouseEvent } from "react";

import { FORM_ANCHOR, NAV_ITEMS } from "@/lib/site";

import { reducedMotion } from "./motion";

// ------------------------------------------------------------------------------------- theme
// "system" follows the operating system; the toggle pins light or dark on <html data-fu-theme>.
// The script in layout.tsx applies a saved choice before the first paint.

const THEME_KEY = "fu_theme";
const THEME_EVENT = "fu:theme";

function isDarkNow(): boolean {
  const pinned = document.documentElement.getAttribute("data-fu-theme");
  if (pinned === "dark") return true;
  if (pinned === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function subscribeTheme(onChange: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  window.addEventListener(THEME_EVENT, onChange);
  return () => {
    media.removeEventListener("change", onChange);
    window.removeEventListener(THEME_EVENT, onChange);
  };
}

function setTheme(theme: "light" | "dark") {
  document.documentElement.setAttribute("data-fu-theme", theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // The choice holds for this page only.
  }
  window.dispatchEvent(new Event(THEME_EVENT));
}

// ------------------------------------------------------------------------------------- start a test
// "Test my website" anywhere goes to the form on the home page. On the home page it scrolls there,
// switches the form to the test tab and puts the cursor in the address field.
export const START_TEST_EVENT = "fu:start-test";

export function goToForm(event: MouseEvent, pathname: string, push: (href: string) => void) {
  event.preventDefault();
  if (pathname !== "/") {
    push(`/#${FORM_ANCHOR}`);
    return;
  }
  const form = document.getElementById(FORM_ANCHOR);
  if (form) {
    window.scrollTo({
      top: form.getBoundingClientRect().top + window.scrollY - 80,
      behavior: reducedMotion() ? "auto" : "smooth",
    });
  }
  window.dispatchEvent(new Event(START_TEST_EVENT));
}

export function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const dark = useSyncExternalStore(subscribeTheme, isDarkNow, () => true);
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const pillRef = useRef<HTMLSpanElement>(null);
  const progressRef = useRef<HTMLSpanElement>(null);

  // The bar fills in once the page scrolls, and the thin line under it shows how far down the page is.
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const y = window.scrollY;
      setScrolled(y > 24);
      const height = document.documentElement.scrollHeight - window.innerHeight;
      if (progressRef.current) {
        progressRef.current.style.transform = `scaleX(${height > 0 ? Math.min(1, y / height) : 0})`;
      }
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: Event) => {
      if (barRef.current && !barRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  function navEnter(event: MouseEvent<HTMLAnchorElement>) {
    const pill = pillRef.current;
    const nav = navRef.current;
    const link = event.currentTarget;
    if (!pill || !nav) return;
    if (link.getAttribute("aria-current") === "page") {
      pill.style.opacity = "0";
      return;
    }
    const a = link.getBoundingClientRect();
    const b = nav.getBoundingClientRect();
    pill.style.left = `${a.left - b.left}px`;
    pill.style.width = `${a.width}px`;
    pill.style.opacity = "1";
  }

  function onNav(event: MouseEvent<HTMLAnchorElement>, href: string) {
    setMenuOpen(false);
    // "How it works" on the home page scrolls rather than reloading.
    if (href.startsWith("/#") && pathname === "/") {
      const target = document.getElementById(href.slice(2));
      if (target) {
        event.preventDefault();
        window.scrollTo({
          top: target.getBoundingClientRect().top + window.scrollY - 80,
          behavior: reducedMotion() ? "auto" : "smooth",
        });
      }
    }
  }

  const themeLabel = dark ? "Switch to light theme" : "Switch to dark theme";

  return (
    <header className="fu-header">
      <div ref={barRef} className="fu-bar" data-scrolled={scrolled}>
        <span aria-hidden className="fu-progress">
          <span ref={progressRef} />
        </span>
        <Link href="/" aria-label="First User home" className="flex items-center gap-2.5 text-ink hover:text-ink">
          <span className="fu-logo-mark">
            <span />
          </span>
          <span className="fu-logo-word">First User</span>
        </Link>

        <nav
          ref={navRef}
          aria-label="Main"
          className="fu-nav fu-wide-only"
          onMouseLeave={() => {
            if (pillRef.current) pillRef.current.style.opacity = "0";
          }}
        >
          <span ref={pillRef} aria-hidden className="fu-nav-pill" />
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className="fu-nav-link"
              aria-current={item.match(pathname) ? "page" : undefined}
              onMouseEnter={navEnter}
              onClick={(event) => onNav(event, item.href)}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex flex-none items-center gap-2">
          <button
            type="button"
            className="fu-burger fu-narrow-only"
            aria-label="Menu"
            aria-expanded={menuOpen}
            aria-controls="fu-menu"
            onClick={(event) => {
              event.stopPropagation();
              setMenuOpen((open) => !open);
            }}
          >
            <span />
            <span />
          </button>
          <button
            type="button"
            className="fu-icon-btn"
            aria-label={themeLabel}
            title={themeLabel}
            onClick={() => setTheme(isDarkNow() ? "light" : "dark")}
            suppressHydrationWarning
          >
            <span aria-hidden suppressHydrationWarning>
              {dark ? "☾" : "☀"}
            </span>
          </button>
          <a
            href={`/#${FORM_ANCHOR}`}
            aria-label="Test my website"
            className="fu-btn fu-cta"
            style={{ paddingLeft: 6, paddingRight: 6 }}
            onClick={(event) => goToForm(event, pathname, router.push)}
          >
            <span className="fu-cta-text">Test my website</span>
            <span aria-hidden className="fu-arrow">
              →
            </span>
          </a>
        </div>

        {menuOpen && (
          <div id="fu-menu" className="fu-menu">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                aria-current={item.match(pathname) ? "page" : undefined}
                onClick={(event) => onNav(event, item.href)}
              >
                {item.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
