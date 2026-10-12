import "server-only";

import { supabase } from "@/lib/supabase";

// A test run started from a brief records which brief it came from (runs.brief_run_id). Both steps are
// best-effort: a database that has not had the "Understand mode" SQL yet still starts the test.

export async function briefExists(briefId: string): Promise<boolean> {
  const { data, error } = await supabase()
    .from("runs")
    .select("id")
    .eq("id", briefId)
    .eq("kind", "understand")
    .maybeSingle();
  if (error) {
    console.error("Looking up the brief failed:", error.message);
    return false;
  }
  return !!data;
}

export async function recordBrief(runId: string, briefId: string): Promise<void> {
  const { error } = await supabase().from("runs").update({ brief_run_id: briefId }).eq("id", runId);
  if (error) console.error("Recording the brief on the run failed:", error.message);
}
