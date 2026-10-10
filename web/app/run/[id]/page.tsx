import type { Metadata } from "next";
import { Suspense } from "react";

import { RunView } from "./run-view";

export const metadata: Metadata = {
  title: "Visit report · First User",
  // Reports are shared by link; keep them out of search results.
  robots: { index: false, follow: false },
};

export default function RunPage({ params }: PageProps<"/run/[id]">) {
  return (
    <Suspense fallback={<p className="text-muted">Loading the run…</p>}>
      {params.then(({ id }) => (
        <RunView id={id} />
      ))}
    </Suspense>
  );
}
