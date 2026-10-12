"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import type { HomeParams } from "@/lib/brief-logic";
import { grid } from "@/lib/css";
import { rememberPendingRun } from "@/lib/pending-run";
import { FORM_ANCHOR } from "@/lib/site";
import type { ApiError } from "@/lib/types";

import { START_TEST_EVENT } from "../site-header";
import { ACCESS, LOOP, type Access } from "./data";
import { setHome, useHome, type Tab } from "./store";

type Field = "url" | "goal" | "startUrl" | "credentials" | "permission" | "success" | "form";
type FormError = { field: Field; title?: string; message: string };

const TITLES: Record<string, string> = {
  queue_full: "The queue is full",
  rate_limited: "You've reached the hourly limit",
  server_error: "Something went wrong",
};

const FIELD_OF: Record<string, Field> = {
  invalid_url: "url",
  goal_too_long: "goal",
  success_too_long: "success",
  invalid_start_url: "startUrl",
  invalid_credentials: "credentials",
  permission_required: "permission",
};

// The address field shows "https://" in front, so a filled-in https address is shown without it.
function withoutHttps(url: string): string {
  return url.replace(/^https:\/\//i, "");
}

export function StartSection({ initial }: { initial: HomeParams }) {
  const router = useRouter();
  const url = useHome((s) => s.url);
  const tab = useHome((s) => s.tab);
  const step = useHome((s) => s.step);
  const [goal, setGoal] = useState(initial.goal);
  const [success, setSuccess] = useState(initial.success);
  const [access, setAccess] = useState<Access>("public");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const urlInput = useRef<HTMLInputElement>(null);

  // Filled in from the address (a suggested journey on a product brief, or "Run it again").
  useEffect(() => {
    const patch: { url?: string; tab: Tab } = { tab: initial.mode };
    if (initial.url) patch.url = withoutHttps(initial.url);
    setHome(patch);
  }, [initial.mode, initial.url]);

  // "Test my website" anywhere on the page lands here, on the test tab, ready to type.
  useEffect(() => {
    const focus = () => {
      setHome({ tab: "test" });
      setTimeout(() => urlInput.current?.focus({ preventScroll: true }), 300);
    };
    window.addEventListener(START_TEST_EVENT, focus);
    if (window.location.hash === `#${FORM_ANCHOR}`) focus();
    return () => window.removeEventListener(START_TEST_EVENT, focus);
  }, []);

  const testing = tab === "test";
  const accessLabel = (ACCESS.find((option) => option.id === access) ?? ACCESS[0]).t.toLowerCase();
  const next = testing
    ? [
        `Opens ${url || "your site"} in a real browser`,
        `Gets in with: ${accessLabel}`,
        `Tries to ${goal ? `"${goal.replace(/^./, (c) => c.toLowerCase())}"` : "reach the goal you write"}`,
        `An independent check confirms ${success ? `"${success}"` : "whether it got there"}`,
        "Report in a few minutes, with a fix prompt per finding",
      ]
    : [
        `Reads the public pages of ${url || "your site"}`,
        "Writes a sourced product brief",
        "Suggests 3–5 journeys you can test in one click",
      ];
  const lit = (i: number) => (i === 0 && !!url) || (i === 1 && testing) || (i === 2 && !!goal) || (i === 3 && !!success);
  const loopOn = Math.floor(step / 2) % 4;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const address = url.trim();
    if (!address) {
      setError({ field: "url", message: testing ? "Enter your app's address." : "Enter the website's address." });
      urlInput.current?.focus();
      return;
    }
    if (testing) return startTest(form, address);
    return startBrief(address);
  }

  async function startTest(form: FormData, address: string) {
    const permission = form.get("permission") === "on";
    // Only the fields of the chosen way in exist in the form, so nothing else is read or sent.
    const startUrl = access === "link" ? String(form.get("startUrl") ?? "").trim() : "";
    const testEmail = access === "account" ? String(form.get("testEmail") ?? "").trim() : "";
    const testPassword = access === "account" ? String(form.get("testPassword") ?? "") : "";
    if (access === "link" && !startUrl) {
      return setError({ field: "startUrl", message: "Enter the demo or guest link, or choose another option." });
    }
    if (access === "account" && (!testEmail || !testPassword)) {
      return setError({ field: "credentials", message: "Enter both a test email and a test password, or choose another option." });
    }
    if (!permission) {
      return setError({ field: "permission", message: "Please confirm you're allowed to test this app." });
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: address,
          goal: goal.trim(),
          briefId: initial.brief || undefined,
          permission,
          successCondition: success.trim() || undefined,
          access,
          startUrl: startUrl || undefined,
          testEmail: testEmail || undefined,
          testPassword: testPassword || undefined,
        }),
      });
      const body = (await response.json().catch(() => null)) as { id?: string } | ApiError | null;
      if (response.ok && body && "id" in body && body.id) {
        rememberPendingRun(body.id, { url: address, goal: goal.trim() });
        router.push(`/run/${body.id}`);
        return;
      }
      const apiError = body && "error" in body ? body : null;
      const code = apiError?.error ?? "server_error";
      setError({
        field: FIELD_OF[code] ?? "form",
        title: TITLES[code],
        message: apiError?.message ?? "Something went wrong on our side. Please try again in a minute.",
      });
    } catch {
      setError({ field: "form", title: "Couldn't reach the server", message: "Check your connection and try again." });
    }
    setSubmitting(false);
  }

  async function startBrief(address: string) {
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/briefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: address }),
      });
      const body = (await response.json().catch(() => null)) as { id?: string } | ApiError | null;
      if (response.ok && body && "id" in body && body.id) {
        router.push(`/brief/${body.id}`);
        return;
      }
      const apiError = body && "error" in body ? body : null;
      const code = apiError?.error ?? "server_error";
      setError({
        field: code === "invalid_url" ? "url" : "form",
        title: TITLES[code],
        message: apiError?.message ?? "Something went wrong on our side. Please try again in a minute.",
      });
    } catch {
      setError({ field: "form", title: "Couldn't reach the server", message: "Check your connection and try again." });
    }
    setSubmitting(false);
  }

  function switchTab(next: Tab) {
    setHome({ tab: next });
    setError(null);
  }

  const fieldError = (field: Field) =>
    error?.field === field ? (
      <p id={`${field}-error`} className="fu-error">
        {error.message}
      </p>
    ) : null;

  return (
    <section id="fu-start" data-reveal="" data-self="0" className="bg-s1" style={{ padding: "var(--section-y-lg) var(--gutter) var(--section-y)" }}>
      <div className="fu-grid items-start" style={grid("420px", "clamp(32px,5cqi,64px)")}>
        <div className="fu-sticky-col flex flex-col gap-6">
          <div data-stagger="">
            <span className="fu-eyebrow mb-4 block">01 · Start a run</span>
            <h2 className="fu-display text-section">
              Tell it what
              <br />
              to try.
            </h2>
          </div>
          <p data-stagger="" className="m-0 max-w-[34em] text-[18px] leading-normal text-ink2 fu-pretty">
            Test one journey now, or let it read your site first and suggest which journeys are worth testing.
          </p>
          <div data-stagger="" className="overflow-hidden rounded-cardsm border-[1.5px] border-ink bg-bg">
            <div className="flex items-center justify-between gap-2.5 border-b border-line px-4 py-3">
              <span className="fu-eyebrow">What happens next</span>
              <span className="flex items-center gap-1.5 font-code text-[12px] font-medium text-ink3">
                <span className="fu-dot-live" />
                Updates as you type
              </span>
            </div>
            <ol className="m-0 list-none py-1.5" aria-live="polite">
              {next.map((text, i) => (
                <li key={i} className="grid items-start gap-3 px-4 py-2.5" style={{ gridTemplateColumns: "28px minmax(0,1fr)" }}>
                  <span
                    className="flex size-6 items-center justify-center rounded-full border-[1.5px] border-ink text-[11px] font-semibold"
                    style={{
                      background: lit(i) ? "var(--acc)" : "var(--s1)",
                      color: lit(i) ? "#0E1320" : "var(--ink)",
                      transition: "background .4s",
                    }}
                  >
                    {i + 1}
                  </span>
                  <span className="text-[15px] leading-[1.45] text-ink [overflow-wrap:anywhere]">{text}</span>
                </li>
              ))}
            </ol>
          </div>
          <div data-stagger="" aria-hidden className="flex flex-wrap gap-2 font-code text-[13px] font-medium text-ink3">
            {LOOP.map((item, i) => {
              const on = i === loopOn;
              return (
                <span key={item.name} className="flex items-center gap-2 whitespace-nowrap">
                  <span
                    className="flex h-[30px] items-center rounded-pill px-3"
                    style={{
                      border: `1.5px solid ${on ? "var(--ink)" : "var(--line)"}`,
                      background: on ? "var(--acc)" : "var(--bg)",
                      color: on ? "var(--on-acc)" : "var(--ink)",
                      transition: "background .4s, border-color .4s",
                    }}
                  >
                    {item.name}
                  </span>
                  {i < 3 && <span>→</span>}
                </span>
              );
            })}
          </div>
        </div>

        <div id={FORM_ANCHOR} data-stagger="" className="overflow-hidden rounded-form border-[1.5px] border-ink bg-s1 shadow-hard-xl">
          <div role="tablist" aria-label="What do you want to do?" className="relative grid grid-cols-2 border-b-[1.5px] border-ink">
            <span
              aria-hidden
              className="absolute -bottom-[1.5px] z-[1] h-1 w-1/2 border-t-[1.5px] border-ink bg-acc"
              style={{ left: testing ? "0%" : "50%", transition: "left .45s var(--e-spring)" }}
            />
            {(
              [
                ["test", "Test my website"],
                ["understand", "Understand this website"],
              ] as const
            ).map(([id, label], i) => {
              const on = tab === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  id={`tab-${id}`}
                  aria-selected={on}
                  aria-controls="fu-form-panel"
                  onClick={() => switchTab(id)}
                  className="flex min-h-14 cursor-pointer items-center justify-center gap-2 border-none px-3.5 py-2.5 text-center text-[15px] font-semibold text-ink"
                  style={{
                    background: on ? "var(--s1)" : "var(--s2)",
                    borderRight: i === 0 ? "1.5px solid var(--ink)" : "none",
                    transition: "background .3s",
                  }}
                >
                  <span className="size-2 flex-none rounded-full" style={{ background: on ? "var(--acc)" : "var(--line)" }} />
                  {label}
                </button>
              );
            })}
          </div>

          <form
            id="fu-form-panel"
            role="tabpanel"
            aria-labelledby={`tab-${tab}`}
            onSubmit={submit}
            noValidate
            className="flex flex-col gap-[18px]"
            style={{ padding: "clamp(20px,2.6cqi,28px)" }}
          >
            {initial.brief && testing && (
              <p className="fu-notice m-0">Filled in from the product brief of this site. Change anything you like before you start.</p>
            )}
            <div className="flex flex-col gap-2">
              <label htmlFor="fu-url" className="fu-label">
                <span className="fu-num">1</span>Website URL
              </label>
              <span className="fu-field-wrap" data-invalid={error?.field === "url"}>
                <span aria-hidden>https://</span>
                <input
                  ref={urlInput}
                  id="fu-url"
                  name="url"
                  inputMode="url"
                  autoComplete="url"
                  placeholder="your-app.com"
                  value={url}
                  onChange={(event) => setHome({ url: event.target.value })}
                  aria-invalid={error?.field === "url"}
                  aria-describedby={error?.field === "url" ? "url-error" : testing ? undefined : "understand-hint"}
                />
              </span>
              {fieldError("url")}
              {!testing && (
                <p id="understand-hint" className="fu-hint">
                  We read the homepage and up to eight more public pages (about, product, pricing, docs and so on), follow the
                  site&apos;s robots.txt, and never sign in.
                </p>
              )}
            </div>

            {testing && (
              <div className="flex flex-col gap-[18px]">
                <div className="flex flex-col gap-2">
                  <label htmlFor="fu-goal" className="fu-label">
                    <span className="fu-num">2</span>What should a new user be able to do?
                  </label>
                  <input
                    id="fu-goal"
                    name="goal"
                    maxLength={500}
                    value={goal}
                    onChange={(event) => setGoal(event.target.value)}
                    placeholder="Create a project and add the first task"
                    aria-invalid={error?.field === "goal"}
                    aria-describedby="goal-hint"
                    className="fu-field"
                  />
                  <p id="goal-hint" className="fu-hint">
                    Leave it empty and the visitor works out what the product does and tries its main feature.
                  </p>
                  {fieldError("goal")}
                </div>
                <div className="flex flex-col gap-2">
                  <label htmlFor="fu-success" className="fu-label">
                    <span className="fu-num">3</span>
                    <span>
                      What does success look like? <span className="font-normal text-ink3">Optional</span>
                    </span>
                  </label>
                  <input
                    id="fu-success"
                    name="successCondition"
                    maxLength={300}
                    value={success}
                    onChange={(event) => setSuccess(event.target.value)}
                    placeholder="A project appears in the dashboard"
                    aria-invalid={error?.field === "success"}
                    aria-describedby="success-hint"
                    className="fu-field"
                  />
                  <p id="success-hint" className="fu-hint">
                    The independent check judges this, not only the wording of the goal.
                  </p>
                  {fieldError("success")}
                </div>
                <fieldset className="m-0 flex min-w-0 flex-col gap-2.5 border-none p-0">
                  <legend className="fu-label mb-2.5 p-0">
                    <span className="fu-num">4</span>How should the visitor get in?
                  </legend>
                  <div role="radiogroup" aria-label="How should the visitor get in?" className="fu-grid" style={grid("200px", "8px")}>
                    {ACCESS.map((option) => {
                      const on = access === option.id;
                      return (
                        <label
                          key={option.id}
                          className="flex cursor-pointer items-start gap-2.5 rounded-field p-3 text-left text-ink"
                          style={{
                            border: `1.5px solid ${on ? "var(--ink)" : "var(--line)"}`,
                            background: on ? "var(--acc-soft)" : "var(--bg)",
                            transform: on ? "translate(-2px,-2px)" : "none",
                            boxShadow: on ? "var(--sh-hard-sm)" : "none",
                            transition: "transform .25s var(--e-bounce), box-shadow .25s, background .25s, border-color .25s",
                          }}
                        >
                          <input
                            type="radio"
                            name="access"
                            value={option.id}
                            checked={on}
                            onChange={() => {
                              setAccess(option.id);
                              setError(null);
                            }}
                            className="peer sr-only"
                          />
                          <span
                            aria-hidden
                            className="mt-0.5 flex size-4 flex-none items-center justify-center rounded-full border-[1.5px] border-ink peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-info"
                          >
                            <span className="size-2 rounded-full bg-ink" style={{ opacity: on ? 1 : 0 }} />
                          </span>
                          <span className="flex flex-col gap-[3px]">
                            <span className="text-[14px] font-semibold">{option.t}</span>
                            <span className="text-[13px] leading-[1.4] text-ink3">{option.d}</span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  <p className="fu-hint">Apps that only offer Google or GitHub login: use a start link.</p>
                  {access === "link" && (
                    <div className="flex flex-col gap-2">
                      <label htmlFor="fu-start-url" className="text-[14px] font-semibold">
                        Start link
                      </label>
                      <input
                        id="fu-start-url"
                        name="startUrl"
                        type="url"
                        inputMode="url"
                        placeholder="https://your-app.com/demo"
                        aria-invalid={error?.field === "startUrl"}
                        aria-describedby="start-hint"
                        className="fu-field fu-field-mono"
                      />
                      <p id="start-hint" className="fu-hint">
                        A demo page, guest mode or preview build that is already past the login. The visit begins here.
                      </p>
                      {fieldError("startUrl")}
                    </div>
                  )}
                  {access === "account" && (
                    <div className="flex flex-col gap-2">
                      <div className="fu-grid" style={grid("180px", "8px")}>
                        <input
                          name="testEmail"
                          type="email"
                          autoComplete="off"
                          placeholder="test@your-app.com"
                          aria-label="Test email"
                          aria-invalid={error?.field === "credentials"}
                          className="fu-field fu-field-mono"
                        />
                        <input
                          name="testPassword"
                          type="password"
                          autoComplete="new-password"
                          placeholder="Password"
                          aria-label="Test password"
                          aria-invalid={error?.field === "credentials"}
                          className="fu-field fu-field-mono"
                        />
                      </div>
                      <p className="fu-hint">Use a throwaway account. It is never shown to the AI and is deleted after the run.</p>
                      {fieldError("credentials")}
                    </div>
                  )}
                  {access === "signup" && (
                    <p className="fu-hint">Works for email-and-password signup without email verification.</p>
                  )}
                </fieldset>
                <div className="flex flex-col gap-2">
                  <label className="flex cursor-pointer items-start gap-3 text-[15px] leading-[1.45]">
                    <input
                      name="permission"
                      type="checkbox"
                      aria-invalid={error?.field === "permission"}
                      className="mt-0.5 size-[18px] flex-none accent-[var(--ink)]"
                    />
                    <span>This is my app or I have permission to test it</span>
                  </label>
                  {fieldError("permission")}
                </div>
              </div>
            )}

            {error?.field === "form" && (
              <div role="alert" className="fu-alert">
                {error.title && <p className="m-0 font-semibold text-bad-ink">{error.title}</p>}
                <p className="m-0 mt-1">{error.message}</p>
              </div>
            )}

            <button type="submit" disabled={submitting} className="fu-btn fu-btn-lg">
              <span>{submitting ? "Starting…" : testing ? "Test my website" : "Understand this website"}</span>
              <span aria-hidden className="fu-arrow fu-arrow-lg fu-nudge">
                →
              </span>
            </button>
            <p className="m-0 text-center text-[14px] leading-normal text-ink3 fu-pretty">
              No QA team required. No pretending a click worked when it didn&apos;t.
            </p>
          </form>
        </div>
      </div>
    </section>
  );
}
