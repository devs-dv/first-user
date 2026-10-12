import type { Metadata } from "next";
import { Suspense } from "react";

import { UUID } from "@/lib/brief-logic";
import { reportMeta, type ReportMetaRun } from "@/lib/page-meta";
import { supabase } from "@/lib/supabase";

import { pageMeta } from "../../meta";

import { RunLoading } from "./run-loading";
import { RunView } from "./run-view";

// The title and share card carry the site and the verdict. Reading the run can fail (a mistyped id, an older
// schema, the database being away); the page then gets a plain title and still renders.
export async function generateMetadata({ params }: PageProps<"/run/[id]">): Promise<Metadata> {
  const { id } = await params;
  let run: ReportMetaRun | null = null;
  if (UUID.test(id)) {
    try {
      const { data } = await supabase().from("runs").select("url, status, outcome, verdict, entry").eq("id", id).maybeSingle();
      run = (data as ReportMetaRun | null) ?? null;
    } catch {
      run = null;
    }
  }
  // Reports are shared by link; keep them out of search results.
  return pageMeta(reportMeta(run), { robots: { index: false, follow: false } });
}

export default function RunPage({ params }: PageProps<"/run/[id]">) {
  return (
    <Suspense
      fallback={<RunLoading />}
    >
      {params.then(({ id }) => (
        <RunView id={id} />
      ))}
    </Suspense>
  );
}
