// The founder brief is behind a switch, off unless NEXT_PUBLIC_FOUNDER_BRIEF is on|1|true|yes. It is a
// NEXT_PUBLIC_ value (it only shows or hides a tab), read when the app is built; the API routes check it too.

const ON = new Set(["on", "1", "true", "yes", "enabled"]);

export function founderFlagFrom(value: string | undefined): boolean {
  return ON.has((value ?? "").trim().toLowerCase());
}

// Written out in full, because Next only inlines NEXT_PUBLIC_ values it can see.
export function founderBriefEnabled(): boolean {
  return founderFlagFrom(process.env.NEXT_PUBLIC_FOUNDER_BRIEF);
}
