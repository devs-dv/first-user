import { UUID } from "@/lib/brief-logic";
import { BRIEF_COLUMNS } from "@/lib/brief-types";
import { supabase } from "@/lib/supabase";

const NO_STORE = { "Cache-Control": "no-store" };

function fail(status: number, error: string, message: string) {
  return Response.json({ error, message }, { status, headers: NO_STORE });
}

export async function GET(_request: Request, ctx: RouteContext<"/api/briefs/[id]">) {
  const { id } = await ctx.params;
  if (!UUID.test(id)) return fail(404, "not_found", "We couldn't find that brief.");

  // Only an understand run is a brief; the visitor's IP hash and the raw worker error stay private.
  const { data, error } = await supabase()
    .from("runs")
    .select(BRIEF_COLUMNS)
    .eq("id", id)
    .eq("kind", "understand")
    .maybeSingle();
  if (error) {
    console.error("Reading brief failed:", error.message);
    return fail(500, "server_error", "Something went wrong on our side. Retrying shortly.");
  }
  if (!data) return fail(404, "not_found", "We couldn't find that brief.");
  return Response.json({ run: data }, { headers: NO_STORE });
}
