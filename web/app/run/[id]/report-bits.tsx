// Small pieces the report's sections share: the mock browser frame around a screenshot, the way-in sentences,
// and number formatting. Every string from a run (model- or site-sourced) is rendered as text.

import type { ReactNode } from "react";

import { pathOf } from "@/lib/report-view";
import type { Entry, LoginDiagnosis, Run } from "@/lib/types";

export function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${parsed.host}${path}${parsed.search}`;
  } catch {
    return url;
  }
}

export function formatCost(cost: number | string | null | undefined): string {
  if (cost === null || cost === undefined || cost === "") return "—";
  const value = Number(cost);
  return Number.isFinite(value) ? `$${value.toFixed(value < 0.1 ? 4 : 2)}` : "—";
}

// The home page's form, filled in with this run's address, goal and success condition.
export function againHref(run: Pick<Run, "url" | "goal" | "success_condition">): string {
  const params = new URLSearchParams({ mode: "test", url: run.url, goal: run.goal });
  if (run.success_condition) params.set("success", run.success_condition);
  return `/?${params.toString()}#fu-form`;
}

// A screenshot (or anything) inside the mock browser of the design, with the page's address on top.
export function BrowserFrame({ url, children, rounded = "field" }: { url: string | null; children: ReactNode; rounded?: "field" | "frame" }) {
  let host = "";
  try {
    host = url ? new URL(url).host : "";
  } catch {
    host = "";
  }
  return (
    <div className="fu-browser" style={{ borderRadius: rounded === "frame" ? "var(--r-frame)" : "var(--r-field)" }}>
      <div className="fu-browser-bar">
        <span className="fu-browser-dot" />
        <span className="truncate">
          {host}
          {pathOf(url)}
        </span>
      </div>
      {children}
    </div>
  );
}

// ------------------------------------------------------------------------------------- how the visitor got in

const MODE_LINES: Record<string, string> = {
  public: "You chose no login, so the visitor looked at what is public.",
  link: "You gave a demo or guest link.",
  account: "You gave a test account.",
  signup: "You let the visitor sign up by itself.",
};
const CHALLENGE_WORDS: Record<string, string> = {
  email_verification: "a code or link sent by email",
  captcha: "a CAPTCHA",
  two_factor: "a two-factor code",
};

// What the page said and returned when the visitor submitted a login or sign-up, as a sentence.
function diagnosisLine(d: LoginDiagnosis): string | null {
  const form = d.stage === "sign_in" ? "test login" : "sign-up";
  const step = d.step !== null ? ` (step ${d.step})` : "";
  const status = d.http_statuses.length ? ` The page's own request returned ${d.http_statuses.join(" and ")}.` : "";
  switch (d.result) {
    case "rejected":
      return d.page_message
        ? `The page rejected the ${form}${step}: “${d.page_message}”.${status}`
        : `The page rejected the ${form}${step} and gave no message.${status}`;
    case "needs_verification":
      return `The visit stopped at the ${form}${step}: it needs ${
        CHALLENGE_WORDS[d.challenge ?? ""] ?? "a verification step"
      }, which the visitor cannot do.`;
    case "no_effect":
      return `Submitting the ${form}${step} had no effect: the page did not change and showed no message.`;
    default:
      return null;
  }
}

export function wayInLines(run: Run): string[] {
  const entry: Entry | null = run.entry;
  const lines: string[] = [];
  const mode = entry?.access_mode ?? run.access_mode;
  if (mode && MODE_LINES[mode]) lines.push(MODE_LINES[mode]);
  lines.push(run.start_url ? `Started at the start link you gave (${displayUrl(run.start_url)}).` : "Started at your app's address.");
  const diagnosis = entry?.diagnosis ?? null;
  if (entry?.test_login === "used") lines.push("Signed in with your test account.");
  else if (entry?.test_login === "failed" && diagnosis?.stage === "sign_in") {
    lines.push(diagnosisLine(diagnosis) ?? "Tried your test account, but the sign-in did not work.");
  } else if (entry?.test_login === "failed") lines.push("Tried your test account, but the sign-in did not work.");
  else if (entry?.test_login === "provided_not_used" || (!entry && run.has_test_login)) {
    lines.push("A test account was provided, but the visitor did not need it.");
  }
  if (entry?.self_signup === "used") {
    lines.push(
      entry.created_account_email
        ? `Created a test account (${entry.created_account_email}) to get in. You may want to delete it.`
        : "Created a test account to get in.",
    );
  } else if (entry?.self_signup === "blocked_third_party") {
    const options = entry.third_party_options.length ? ` (${entry.third_party_options.join(", ")})` : "";
    lines.push(`Only third-party sign-in was offered${options}. The visitor never uses those.`);
  } else if (entry?.self_signup === "blocked_verification" || entry?.self_signup === "failed") {
    const sentence = diagnosis?.stage === "sign_up" ? diagnosisLine(diagnosis) : null;
    lines.push(
      sentence ??
        (entry.self_signup === "blocked_verification"
          ? "Tried to sign up, but the app needs email verification, which the visitor can't do."
          : "Tried to sign up with a made-up test account, but the form did not accept it."),
    );
  }
  if (entry?.bot_check) {
    lines.push(
      `The site showed a bot check (“${entry.bot_check.phrase}”). The visitor never tries to get past those, so the visit stopped there.`,
    );
  }
  // A login written on the page itself is a way in too, and never "no login".
  if (entry?.page_login === "shown_on_page") {
    lines.push("Typed a login that was written on the page itself, a demo login for visitors. It was not one you gave.");
  } else if (entry?.page_login === "typed") {
    lines.push("Typed a password into a login form. It was not one you gave.");
  }
  const usedAnything =
    !!run.start_url ||
    run.has_test_login ||
    (!!entry && (entry.self_signup !== "not_used" || (entry.page_login ?? "not_used") !== "not_used"));
  if (!usedAnything) lines.push("No login was used: the visitor saw only what is public.");
  return lines;
}
