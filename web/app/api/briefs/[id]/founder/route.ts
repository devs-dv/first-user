import { UUID } from "@/lib/brief-logic";
import { founderBriefEnabled } from "@/lib/founder-flag";
import { FOUNDER_COLUMNS } from "@/lib/founder-types";
import { supabase } from "@/lib/supabase";
import { MAX_QUEUED, rateLimited, runsPerHour } from "@/lib/run-limits";
import { clientIp, hashIp } from "@/lib/visitor";

const NO_STORE = { "Cache-Control": "no-store" };

function fail(status: number, error: string, message: string, headers?: HeadersInit) {
  return Response.json({ error, message }, { status, headers: { ...NO_STORE, ...headers } });
}

// The newest founder brief of this product brief, or { run: null } if none was asked for yet.
export async function GET(_request: Request, ctx: RouteContext<"/api/briefs/[id]/founder">) {
  if (!founderBriefEnabled()) return fail(404, "not_found", "Not available.");
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that brief.");

  const { data, error } = await supabase()
    .from("runs")
    .select(FOUNDER_COLUMNS)
    .eq("brief_run_id", id)
    .eq("kind", "founder_brief")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) {
    console.error("Reading founder brief failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Retrying shortly.");
  }
  return Response.json({ run: data ?? null }, { headers: NO_STORE });
}

// Ask for the founder brief. It is written by the worker from the stored product brief, on demand.
export async function POST(request: Request, ctx: RouteContext<"/api/briefs/[id]/founder">) {
  if (!founderBriefEnabled()) return fail(404, "not_found", "Not available.");
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that brief.");

  const perHour = runsPerHour();
  const { data, error } = await supabase().rpc("enqueue_founder_brief_run", {
    p_brief_id: id,
    p_ip_hash: hashIp(clientIp(request.headers)),
    p_max_queued: MAX_QUEUED,
    p_max_per_hour: perHour,
  });
  if (error) {
    console.error("enqueue_founder_brief_run failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  const result = data as { id?: string; error?: string; retry_after_seconds?: number };
  if (result.error === "no_brief") return fail(404, "not_found", "That product brief isn't finished yet.");
  if (result.error === "queue_full") {
    return fail(503, "queue_full", "Too many runs are waiting right now. Please try again in a few minutes.", {
      "Retry-After": "300",
    });
  }
  if (result.error === "rate_limited") return rateLimited(perHour, result.retry_after_seconds, NO_STORE);
  if (!result.id) {
    console.error("enqueue_founder_brief_run returned no id");
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  return Response.json({ id: result.id }, { status: 201, headers: NO_STORE });
}
