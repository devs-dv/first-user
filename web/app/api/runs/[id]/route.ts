import { supabase } from "@/lib/supabase";
import { FRICTION_COLUMNS, RUN_COLUMNS, RUN_COLUMNS_BEFORE_FINDINGS, STEP_COLUMNS } from "@/lib/types";

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
  const [firstRun, steps, frictions] = await Promise.all([
    db.from("runs").select(RUN_COLUMNS).eq("id", id).maybeSingle(),
    db.from("steps").select(STEP_COLUMNS).eq("run_id", id).order("idx"),
    db.from("frictions").select(FRICTION_COLUMNS).eq("run_id", id).order("step_idx").order("id"),
  ]);

  // PostgREST says a column is missing (42703 or PGRST204) when supabase/schema.sql has not been re-run
  // since the report writer was added: read the run without the newest columns rather than fail.
  let runError = firstRun.error;
  let runRow: Record<string, unknown> | null = firstRun.data;
  if (runError && /42703|PGRST204|column/i.test(`${runError.code} ${runError.message}`)) {
    const older = await db.from("runs").select(RUN_COLUMNS_BEFORE_FINDINGS).eq("id", id).maybeSingle();
    runError = older.error;
    runRow = older.data ? { ...(older.data as unknown as Record<string, unknown>), access_mode: null, findings: null } : null;
  }

  const error = runError ?? steps.error ?? frictions.error;
  if (error) {
    console.error("Reading run failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Retrying shortly.");
  }
  if (!runRow) return fail(404, "not_found", "We couldn't find that run.");

  // A failed run's reason is an internal error message (API or browser failure), not a finding.
  const runData = runRow.status === "failed" ? { ...runRow, reason: null } : runRow;
  return Response.json({ run: runData, steps: steps.data, frictions: frictions.data }, { headers: NO_STORE });
}
