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
    <Suspense fallback={<main className="fu-page"><p className="m-0 font-code text-[13px] text-ink3">Loading the report…</p></main>}>
      {params.then(({ id }) => (
        <RunView id={id} />
      ))}
    </Suspense>
  );
}
