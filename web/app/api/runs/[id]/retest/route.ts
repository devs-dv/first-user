import { readReportFlags } from "@/lib/report-flags";
import { planRetest, type OriginalForRetest } from "@/lib/retest";
import { supabase } from "@/lib/supabase";
import { checkTargetUrl } from "@/lib/target-url";
import { MAX_QUEUED, rateLimited, runsPerHour } from "@/lib/run-limits";
import { clientIp, hashIp } from "@/lib/visitor";

// Check again: queue a new run with the same URL, goal, way in, start link and success condition as a
// finished one, linked to it (retest_of). It goes through the same database function as any new run, so
// it has the same limits, and its addresses get the same checks.

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function fail(status: number, error: string, message: string, headers?: HeadersInit) {
  return Response.json({ error, message }, { status, headers });
}

export async function POST(request: Request, ctx: { params: Promise<{ id: string }> }) {
  if (!readReportFlags("").checkAgain) return fail(404, "not_found", "Check again is not available.");
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that run.");

  let body: Record<string, unknown> = {};
  try {
    body = ((await request.json()) ?? {}) as Record<string, unknown>;
  } catch {
    body = {};
  }

  // Only what a retest needs. The test login is not in this row, and is never read from run_secrets.
  const db = supabase();
  const { data, error } = await db
    .from("runs")
    .select("id, url, goal, access_mode, start_url, success_condition, has_test_login, status, retest_of")
    .eq("id", id)
    .maybeSingle();
  if (error) {
    console.error("Reading the original run failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  if (!data) return fail(404, "not_found", "We couldn't find that run.");

  const plan = planRetest(data as OriginalForRetest, body);
  if (!plan.ok) return fail(plan.status, plan.error, plan.message);

  // The same address checks as a new run, on both addresses.
  const target = await checkTargetUrl(plan.args.p_url);
  if (!target.ok) return fail(400, "invalid_url", target.message);
  let start: string | null = null;
  if (plan.args.p_start_url) {
    const checked = await checkTargetUrl(plan.args.p_start_url);
    if (!checked.ok) return fail(400, "invalid_start_url", checked.message);
    start = checked.url;
  }
  if (plan.needsLogin && (!target.url.startsWith("https://") || (start && !start.startsWith("https://")))) {
    return fail(400, "invalid_credentials", "A test login can only be used with https:// addresses.");
  }

  const perHour = runsPerHour();
  const { data: queued, error: rpcError } = await db.rpc("enqueue_web_run", {
    ...plan.args,
    p_url: target.url,
    p_start_url: start,
    p_ip_hash: hashIp(clientIp(request.headers)),
    p_max_queued: MAX_QUEUED,
    p_max_per_hour: perHour,
  });
  if (rpcError) {
    // The message names the failure, never the arguments.
    console.error("enqueue_web_run (retest) failed:", rpcError.message);
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  const result = queued as { id?: string; error?: string; retry_after_seconds?: number };
  if (result.error === "queue_full") {
    return fail(503, "queue_full", "Too many runs are waiting right now. Please try again in a few minutes.", {
      "Retry-After": "300",
    });
  }
  if (result.error === "rate_limited") return rateLimited(perHour, result.retry_after_seconds);
  if (result.error === "original_not_found") return fail(404, "not_found", "We couldn't find that run.");
  if (!result.id) {
    console.error("enqueue_web_run (retest) returned no id");
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  return Response.json({ id: result.id }, { status: 201 });
}
