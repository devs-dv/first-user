import { supabase } from "@/lib/supabase";
import { checkTargetUrl } from "@/lib/target-url";
import { clientIp, hashIp } from "@/lib/visitor";

const DEFAULT_GOAL = "Work out what this product does and try its main feature as a first-time visitor.";
const MAX_GOAL_LENGTH = 500;
const MAX_QUEUED = 20;
const MAX_RUNS_PER_HOUR = 5;

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
  const { url, goal, permission } = (body ?? {}) as Record<string, unknown>;

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

  const target = await checkTargetUrl(url);
  if (!target.ok) return fail(400, "invalid_url", target.message);

  const { data, error } = await supabase().rpc("enqueue_web_run", {
    p_url: target.url,
    p_goal: goalText || DEFAULT_GOAL,
    p_ip_hash: hashIp(clientIp(request.headers)),
    p_max_queued: MAX_QUEUED,
    p_max_per_hour: MAX_RUNS_PER_HOUR,
  });
  if (error) {
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
  if (result.error === "rate_limited") {
    const seconds = Math.max(60, result.retry_after_seconds ?? 3600);
    const minutes = Math.ceil(seconds / 60);
    return fail(
      429,
      "rate_limited",
      `You've started ${MAX_RUNS_PER_HOUR} runs in the last hour. You can start another in about ${minutes} minute${minutes === 1 ? "" : "s"}.`,
      { "Retry-After": String(seconds) },
    );
  }
  if (!result.id) {
    console.error("enqueue_web_run returned no id");
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  return Response.json({ id: result.id }, { status: 201 });
}
