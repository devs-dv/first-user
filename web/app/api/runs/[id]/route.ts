import { supabase } from "@/lib/supabase";
import { FRICTION_COLUMNS, RUN_COLUMNS, STEP_COLUMNS } from "@/lib/types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NO_STORE = { "Cache-Control": "no-store" };

function fail(status: number, error: string, message: string) {
  return Response.json({ error, message }, { status, headers: NO_STORE });
}

export async function GET(_request: Request, ctx: RouteContext<"/api/runs/[id]">) {
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that run.");

  // Only selected columns: the visitor's IP hash and the raw worker error stay private.
  const db = supabase();
  const [run, steps, frictions] = await Promise.all([
    db.from("runs").select(RUN_COLUMNS).eq("id", id).maybeSingle(),
    db.from("steps").select(STEP_COLUMNS).eq("run_id", id).order("idx"),
    db.from("frictions").select(FRICTION_COLUMNS).eq("run_id", id).order("step_idx").order("id"),
  ]);

  const error = run.error ?? steps.error ?? frictions.error;
  if (error) {
    console.error("Reading run failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Retrying shortly.");
  }
  if (!run.data) return fail(404, "not_found", "We couldn't find that run.");

  // A failed run's reason is an internal error message (API or browser failure), not a finding.
  const runData = run.data.status === "failed" ? { ...run.data, reason: null } : run.data;
  return Response.json({ run: runData, steps: steps.data, frictions: frictions.data }, { headers: NO_STORE });
}
