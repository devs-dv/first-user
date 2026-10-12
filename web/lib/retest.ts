// What a "Check again" run takes from its original, and what it must never take.
//
// A retest has the same URL, goal, way in, start link and success condition as the original. A test login
// is never stored after a run, so it is never copied: if the original used one, the founder gives it
// again for this check, and it travels only in the body of that one request, to the database function
// that keeps it until the worker claims the run. Pure, so it is tested without a server.

import type { AccessMode, Run } from "./types.ts";

export type OriginalForRetest = Pick<
  Run,
  "id" | "url" | "goal" | "access_mode" | "start_url" | "success_condition" | "has_test_login" | "status"
> & { retest_of: string | null };

export type RetestBody = { testEmail?: unknown; testPassword?: unknown };

export type RetestArguments = {
  p_url: string;
  p_goal: string;
  p_start_url: string | null;
  p_test_email: string | null;
  p_test_password: string | null;
  p_access_mode: AccessMode;
  p_success_condition: string | null;
  p_retest_of: string;
};

export type RetestPlan =
  | { ok: true; args: RetestArguments; needsLogin: boolean }
  | { ok: false; status: number; error: string; message: string };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_EMAIL = 254;
const MAX_PASSWORD = 200;

// The way in the original used. Runs from before the choice existed are read from their fields.
export function accessModeOf(original: OriginalForRetest): AccessMode {
  if (original.access_mode) return original.access_mode;
  if (original.has_test_login) return "account";
  return original.start_url ? "link" : "public";
}

export function planRetest(original: OriginalForRetest, body: RetestBody): RetestPlan {
  if (original.status !== "done") {
    return { ok: false, status: 409, error: "not_finished", message: "Only a finished report can be checked again." };
  }
  const mode = accessModeOf(original);
  const needsLogin = mode === "account" || original.has_test_login;

  let email: string | null = null;
  let password: string | null = null;
  if (needsLogin) {
    const { testEmail, testPassword } = body;
    if (typeof testEmail !== "string" || typeof testPassword !== "string" || !testEmail.trim() || !testPassword) {
      return {
        ok: false,
        status: 400,
        error: "test_login_required",
        message:
          "The original visit used a test login. Test logins are never kept, so give one again for this check.",
      };
    }
    email = testEmail.trim();
    password = testPassword;
    if (email.length > MAX_EMAIL || !EMAIL.test(email)) {
      return { ok: false, status: 400, error: "invalid_credentials", message: "That doesn't look like an email address." };
    }
    if (password.length > MAX_PASSWORD) {
      return {
        ok: false,
        status: 400,
        error: "invalid_credentials",
        message: `Keep the test password under ${MAX_PASSWORD} characters.`,
      };
    }
  }
  // Anything sent when no login is needed is ignored, not forwarded.

  return {
    ok: true,
    needsLogin,
    args: {
      p_url: original.url,
      p_goal: original.goal,
      p_start_url: mode === "link" ? original.start_url : null,
      p_test_email: email,
      p_test_password: password,
      p_access_mode: needsLogin ? "account" : mode,
      p_success_condition: original.success_condition || null,
      // Always the original, never a retest of a retest: the old findings are the original's.
      p_retest_of: original.retest_of ?? original.id,
    },
  };
}
