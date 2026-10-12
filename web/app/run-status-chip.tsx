// A run's status as a small chip: waiting or running while it goes, then the verdict in its own colour
// (lib/verdict-look.ts). A brief that is ready or could not be read gets its own words.

import type { RunStatus, VerdictKind } from "@/lib/types";
import { VERDICT_LOOK } from "@/lib/verdict-look";

export function RunStatusChip({
  status,
  verdictKind,
  brief = false,
}: {
  status: RunStatus;
  verdictKind: VerdictKind | null;
  brief?: boolean;
}) {
  if (status === "queued" || status === "running") {
    const running = status === "running";
    return (
      <span className="fu-chip fu-chip-word bg-s2 text-ink">
        {/* The blink stops under prefers-reduced-motion (tokens.css). */}
        <span
          aria-hidden
          className="size-2 rounded-full"
          style={{ background: running ? "var(--pass)" : "var(--ink4)", animation: running ? "fuBlink 1.6s ease-in-out infinite" : undefined }}
        />
        {running ? "Running" : "Waiting"}
      </span>
    );
  }
  if (brief) {
    const ready = status === "done";
    return (
      <span className="fu-chip fu-chip-word" style={{ background: ready ? "var(--green-soft)" : "var(--s2)", color: ready ? "var(--green-ink)" : "var(--ink3)" }}>
        {ready ? "Brief ready" : "Couldn't read"}
      </span>
    );
  }
  const look = VERDICT_LOOK[verdictKind ?? (status === "failed" ? "our_failure" : "unconfirmed")];
  return (
    <span
      className="fu-chip fu-chip-word"
      style={{ background: look.bg, color: look.fg, border: look.border === "dashed" ? "1px dashed var(--ink3)" : "1px solid transparent" }}
    >
      {look.label}
    </span>
  );
}
