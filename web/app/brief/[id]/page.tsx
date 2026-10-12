import type { Metadata } from "next";
import { Suspense } from "react";

import { BriefView } from "./brief-view";

export const metadata: Metadata = {
  title: "Product brief · First User",
  // Briefs are shared by link; keep them out of search results.
  robots: { index: false, follow: false },
};

export default function BriefPage({ params }: PageProps<"/brief/[id]">) {
  return (
    <Suspense fallback={<p className="text-muted">Loading the brief…</p>}>
      {params.then(({ id }) => (
        <BriefView id={id} />
      ))}
    </Suspense>
  );
}
