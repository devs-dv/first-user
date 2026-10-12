import { UUID } from "@/lib/brief-logic";
import { listedVerdictKind, type BriefTestRun } from "@/lib/journey-progress";
import { supabase } from "@/lib/supabase";
import type { Outcome, RunStatus } from "@/lib/types";

const NO_STORE = { "Cache-Control": "no-store" };

function fail(status: number, error: string, message: string) {
  return Response.json({ error, message }, { status, headers: NO_STORE });
}

// The test runs started from one brief (runs.brief_run_id), newest first: id, goal, status and verdict kind,
// nothing else of the run. Founder briefs share the column, so only test runs are listed.
export async function GET(_request: Request, ctx: RouteContext<"/api/briefs/[id]/runs">) {
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that brief.");

  const { data, error } = await supabase()
    .from("runs")
    .select("id, goal, status, outcome, verdict_kind:verdict->>kind, bot_check:entry->bot_check")
    .eq("brief_run_id", id)
    .eq("kind", "test")
    .order("created_at", { ascending: false })
    .limit(50);
  if (error) {
    console.error("Listing the brief's runs failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Retrying shortly.");
  }
  const runs: BriefTestRun[] = (data ?? []).map((row) => {
    const status = row.status as RunStatus;
    return {
      id: row.id as string,
      goal: (row.goal as string | null) ?? "",
      status,
      verdict_kind: listedVerdictKind({
        status,
        verdict_kind: (row.verdict_kind as string | null) ?? null,
        outcome: (row.outcome as Outcome | null) ?? null,
        bot_check: row.bot_check,
      }),
    };
  });
  return Response.json({ runs }, { headers: NO_STORE });
}
