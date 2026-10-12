"use client";

import { useSyncExternalStore } from "react";

import { idFromPath, parsePendingRun, pendingRunSnapshot } from "@/lib/pending-run";

import { LiveRun } from "./live-run";

const noSubscription = () => () => {};

// The whole page before the run page's code and first answer arrive (the route's loading state): the run is
// queued, with the address and goal the form remembered, when there are some.
export function RunLoading() {
  const id = useSyncExternalStore(noSubscription, idFromPath, () => "");
  const pending = parsePendingRun(useSyncExternalStore(noSubscription, () => pendingRunSnapshot(idFromPath()), () => null));
  return (
    <main className="fu-page" style={{ gap: "var(--block-gap)" }}>
      <LiveRun run={null} steps={[]} pending={pending} id={id || undefined} />
    </main>
  );
}
