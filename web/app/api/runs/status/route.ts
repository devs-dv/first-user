import { UUID } from "@/lib/brief-logic";
import { listedVerdictKind, RECENT_MAX } from "@/lib/journey-progress";
import { supabase } from "@/lib/supabase";
import type { Outcome, RunStatus } from "@/lib/types";

const NO_STORE = { "Cache-Control": "no-store" };

// The status of up to ten runs at once, for the home page's "Your recent runs": id, kind, status and verdict
// kind only. GET /api/runs/status?ids=<id>,<id>
export async function GET(request: Request) {
  const raw = new URL(request.url).searchParams.get("ids") ?? "";
  const ids = [...new Set(raw.split(",").filter((id) => UUID.test(id)))].slice(0, RECENT_MAX);
  if (ids.length === 0) return Response.json({ runs: [] }, { headers: NO_STORE });

  const { data, error } = await supabase()
    .from("runs")
    .select("id, kind, status, outcome, verdict_kind:verdict->>kind, bot_check:entry->bot_check")
    .in("id", ids)
    .in("kind", ["test", "understand"]);
  if (error) {
    console.error("Reading run statuses failed:", error.message);
    return Response.json({ error: "server_error", message: "Something went wrong on our side." }, { status: 500, headers: NO_STORE });
  }
  const runs = (data ?? []).map((row) => {
    const status = row.status as RunStatus;
    return {
      id: row.id as string,
      kind: row.kind as string,
      status,
      verdict_kind:
        row.kind === "test"
          ? listedVerdictKind({
              status,
              verdict_kind: (row.verdict_kind as string | null) ?? null,
              outcome: (row.outcome as Outcome | null) ?? null,
              bot_check: row.bot_check,
            })
          : null,
    };
  });
  return Response.json({ runs }, { headers: NO_STORE });
}
