import type { Metadata } from "next";
import { Suspense } from "react";

import { LiveRun } from "./live-run";
import { RunView } from "./run-view";

export const metadata: Metadata = {
  title: "Visit report · First User",
  // Reports are shared by link; keep them out of search results.
  robots: { index: false, follow: false },
};

export default function RunPage({ params }: PageProps<"/run/[id]">) {
  return (
    <Suspense
      fallback={
        <main className="fu-page" style={{ gap: "var(--block-gap)" }}>
          <LiveRun run={null} steps={[]} />
        </main>
      }
    >
      {params.then(({ id }) => (
        <RunView id={id} />
      ))}
    </Suspense>
  );
}
