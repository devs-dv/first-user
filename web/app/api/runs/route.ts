import { briefExists, recordBrief } from "@/lib/brief-link";
import { UUID } from "@/lib/brief-logic";
import { supabase } from "@/lib/supabase";
import { checkTargetUrl } from "@/lib/target-url";
import { MAX_QUEUED, rateLimited, runsPerHour } from "@/lib/run-limits";
import { clientIp, hashIp } from "@/lib/visitor";

const DEFAULT_GOAL = "Work out what this product does and try its main feature as a first-time visitor.";
const MAX_GOAL_LENGTH = 500;
const MAX_EMAIL_LENGTH = 254;
const MAX_PASSWORD_LENGTH = 200;
const MAX_SUCCESS_LENGTH = 300;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ACCESS_MODES = ["public", "link", "account", "signup"] as const;
type AccessMode = (typeof ACCESS_MODES)[number];

function fail(status: number, error: string, message: string, headers?: HeadersInit) {
  return Response.json({ error, message }, { status, headers });
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return fail(400, "invalid_request", "The request could not be read. Reload the page and try again.");
  }
  const { url, goal, permission, access, startUrl, testEmail, testPassword, successCondition, briefId } = (body ??
    {}) as Record<string, unknown>;

  if (permission !== true) {
    return fail(400, "permission_required", "Confirm that this is your app or that you have permission to test it.");
  }
  if (typeof url !== "string") {
    return fail(400, "invalid_url", "Enter your app's address.");
  }
  if (goal !== undefined && goal !== null && typeof goal !== "string") {
    return fail(400, "invalid_request", "The goal must be text.");
  }
  const goalText = (goal ?? "").trim();
  if (goalText.length > MAX_GOAL_LENGTH) {
    return fail(400, "goal_too_long", `Keep the goal under ${MAX_GOAL_LENGTH} characters.`);
  }

  // Optional: what success looks like, in the founder's words. The visitor is told it and the independent
  // check judges it. Plain text only, never used as an address or in a query.
  if (successCondition !== undefined && successCondition !== null && typeof successCondition !== "string") {
    return fail(400, "invalid_request", "What success looks like must be text.");
  }
  const success = (successCondition ?? "").replace(/\s+/g, " ").trim();
  if (success.length > MAX_SUCCESS_LENGTH) {
    return fail(400, "success_too_long", `Keep what success looks like under ${MAX_SUCCESS_LENGTH} characters.`);
  }
  // A test started from a product brief (Understand mode) says which brief it came from.
  if (briefId !== undefined && briefId !== null && briefId !== "" && (typeof briefId !== "string" || !UUID.test(briefId))) {
    return fail(400, "invalid_request", "That brief link is not valid.");
  }

  const target = await checkTargetUrl(url);
  if (!target.ok) return fail(400, "invalid_url", target.message);

  // How the visitor gets in. A request without it (an older page still open in a browser) is read from
  // its fields; with none, it is "No login", the form's default. Never "signup", which only a choice gives.
  let mode: AccessMode;
  if (access === undefined || access === null || access === "") {
    mode = testEmail || testPassword ? "account" : startUrl ? "link" : "public";
  } else if (typeof access === "string" && (ACCESS_MODES as readonly string[]).includes(access)) {
    mode = access as AccessMode;
  } else {
    return fail(400, "invalid_access", "Choose how the visitor should get in.");
  }

  // A start link past the login, with the same address checks as the main address. Only the
  // fields of the chosen option are used; the others are ignored.
  let start: string | null = null;
  if (mode === "link") {
    if (typeof startUrl !== "string" || startUrl.trim() === "") {
      return fail(400, "invalid_start_url", "Enter the demo or guest link, or choose another option.");
    }
    const checked = await checkTargetUrl(startUrl);
    if (!checked.ok) return fail(400, "invalid_start_url", checked.message);
    start = checked.url;
  }

  // Optional: a throwaway test login. Both or neither. The values are only passed to the database
  // function below; they are never logged, returned or stored on the run itself.
  let email: string | null = null;
  let password: string | null = null;
  if (mode === "account") {
    if (typeof testEmail !== "string" || typeof testPassword !== "string") {
      return fail(400, "invalid_credentials", "Enter a test email and a test password.");
    }
    if (testEmail.trim() === "" || testPassword === "") {
      return fail(400, "invalid_credentials", "Enter both a test email and a test password, or choose another option.");
    }
    email = (testEmail as string).trim();
    password = testPassword as string;
    if (email.length > MAX_EMAIL_LENGTH || !EMAIL.test(email)) {
      return fail(400, "invalid_credentials", "That doesn't look like an email address.");
    }
    if (password.length > MAX_PASSWORD_LENGTH) {
      return fail(400, "invalid_credentials", `Keep the test password under ${MAX_PASSWORD_LENGTH} characters.`);
    }
    // Typing a password over plain http would expose it on the network.
    if (!target.url.startsWith("https://") || (start && !start.startsWith("https://"))) {
      return fail(400, "invalid_credentials", "A test login can only be used with https:// addresses.");
    }
  }

  const perHour = runsPerHour();
  const { data, error } = await supabase().rpc("enqueue_web_run", {
    p_url: target.url,
    p_goal: goalText || DEFAULT_GOAL,
    p_ip_hash: hashIp(clientIp(request.headers)),
    p_max_queued: MAX_QUEUED,
    p_max_per_hour: perHour,
    p_start_url: start,
    p_test_email: email,
    p_test_password: password,
    p_access_mode: mode,
    p_success_condition: success || null,
  });
  if (error) {
    // The message names the failure, never the arguments.
    console.error("enqueue_web_run failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }

  const result = data as { id?: string; error?: string; retry_after_seconds?: number };
  if (result.error === "queue_full") {
    return fail(
      503,
      "queue_full",
      "Too many runs are waiting right now. Please try again in a few minutes.",
      { "Retry-After": "300" },
    );
  }
  if (result.error === "rate_limited") return rateLimited(perHour, result.retry_after_seconds);
  if (!result.id) {
    console.error("enqueue_web_run returned no id");
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  if (typeof briefId === "string" && briefId && (await briefExists(briefId))) {
    await recordBrief(result.id, briefId);
  }
  return Response.json({ id: result.id }, { status: 201 });
}
