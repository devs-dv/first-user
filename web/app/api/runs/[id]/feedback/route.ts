import { UUID } from "@/lib/brief-logic";
import { findingIds, parseFeedback } from "@/lib/feedback-logic";
import { supabase } from "@/lib/supabase";
import { clientIp, hashIp } from "@/lib/visitor";

const NO_STORE = { "Cache-Control": "no-store" };

function fail(status: number, error: string, message: string) {
  return Response.json({ error, message }, { status, headers: NO_STORE });
}

// One vote per finding per visitor (the keyed IP hash the rate limit uses); a later vote replaces the
// earlier one. Only a finished test run's own findings can be voted on. Nothing else about the visitor
// is kept, and the vote is stored, not sent anywhere else.
export async function POST(request: Request, ctx: RouteContext<"/api/runs/[id]/feedback">) {
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that run.");

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return fail(400, "invalid_request", "The request could not be read.");
  }
  const parsed = parseFeedback(body);
  if (!parsed.ok) return fail(400, parsed.error, parsed.message);
  const { findingId, verdict } = parsed.value;

  const db = supabase();
  const { data: run, error: readError } = await db
    .from("runs")
    .select("id, kind, status, findings")
    .eq("id", id)
    .maybeSingle();
  if (readError) {
    console.error("Reading run for feedback failed:", readError.message);
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  if (!run || (run.kind && run.kind !== "test")) return fail(404, "not_found", "We couldn't find that run.");
  if (run.status !== "done" && run.status !== "failed") {
    return fail(409, "not_ready", "This run hasn't finished yet.");
  }
  if (!findingIds(run.findings as never).includes(findingId)) {
    return fail(404, "finding_not_found", "That finding isn't in this report.");
  }

  const { error } = await db.rpc("record_finding_feedback", {
    p_run_id: id,
    p_finding_id: findingId,
    p_verdict: verdict,
    p_ip_hash: hashIp(clientIp(request.headers)),
  });
  if (error) {
    console.error("record_finding_feedback failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Please try again in a minute.");
  }
  return Response.json({ ok: true, findingId, verdict }, { status: 200, headers: NO_STORE });
}
