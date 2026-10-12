import type { Metadata } from "next";
import { Suspense } from "react";

import { UUID } from "@/lib/brief-logic";
import { briefMeta } from "@/lib/page-meta";
import { supabase } from "@/lib/supabase";

import { pageMeta } from "../../meta";

import { BriefView } from "./brief-view";
import { BriefLoading } from "./brief-waiting";

// The title and share card name the site. If the brief cannot be read the page gets a plain title and still renders.
export async function generateMetadata({ params }: PageProps<"/brief/[id]">): Promise<Metadata> {
  const { id } = await params;
  let url: string | null = null;
  if (UUID.test(id)) {
    try {
      const { data } = await supabase().from("runs").select("url").eq("id", id).maybeSingle();
      url = typeof data?.url === "string" ? data.url : null;
    } catch {
      url = null;
    }
  }
  // Briefs are shared by link; keep them out of search results.
  return pageMeta(briefMeta(url), { robots: { index: false, follow: false } });
}

export default function BriefPage({ params }: PageProps<"/brief/[id]">) {
  return (
    <Suspense fallback={<BriefLoading />}>
      {params.then(({ id }) => (
        <BriefView id={id} />
      ))}
    </Suspense>
  );
}
