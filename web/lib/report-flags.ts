// Switches for the sections added by Report v2, so any of them can be hidden if it misbehaves.
//
//   NEXT_PUBLIC_REPORT_V2           "off" hides every Report v2 section at once
//   NEXT_PUBLIC_REPORT_V2_ANSWERS   the three answers at the top
//   NEXT_PUBLIC_REPORT_V2_VERDICT   the verdict card (the old outcome box is shown instead)
//   NEXT_PUBLIC_REPORT_V2_LABELS    the observed / verified / recommendation labels
//   NEXT_PUBLIC_REPORT_V2_CRITERIA  acceptance criteria and retest under each finding
//   NEXT_PUBLIC_REPORT_V2_FACTS     the "How this report was made" panel
//   NEXT_PUBLIC_REPORT_V2_SUCCESS   the success-condition line
//
// All on by default. These are not secrets (they only hide parts of a page), so they are NEXT_PUBLIC_
// variables, read when the app is built. For an immediate switch with no rebuild, add `?report=basic` to
// the report's address: it hides all of them for that view.

export type ReportFlags = {
  answers: boolean;
  verdict: boolean;
  labels: boolean;
  criteria: boolean;
  facts: boolean;
  success: boolean;
};

const OFF = new Set(["off", "false", "0", "no", "hide", "hidden"]);

function on(value: string | undefined): boolean {
  return !OFF.has((value ?? "").trim().toLowerCase());
}

export function flagsFrom(
  env: { master?: string; answers?: string; verdict?: string; labels?: string; criteria?: string; facts?: string; success?: string },
  search = "",
): ReportFlags {
  const master = on(env.master) && new URLSearchParams(search).get("report") !== "basic";
  return {
    answers: master && on(env.answers),
    verdict: master && on(env.verdict),
    labels: master && on(env.labels),
    criteria: master && on(env.criteria),
    facts: master && on(env.facts),
    success: master && on(env.success),
  };
}

// Each variable is named in full, because Next only inlines NEXT_PUBLIC_ values it can see written out.
export function readReportFlags(search = ""): ReportFlags {
  return flagsFrom(
    {
      master: process.env.NEXT_PUBLIC_REPORT_V2,
      answers: process.env.NEXT_PUBLIC_REPORT_V2_ANSWERS,
      verdict: process.env.NEXT_PUBLIC_REPORT_V2_VERDICT,
      labels: process.env.NEXT_PUBLIC_REPORT_V2_LABELS,
      criteria: process.env.NEXT_PUBLIC_REPORT_V2_CRITERIA,
      facts: process.env.NEXT_PUBLIC_REPORT_V2_FACTS,
      success: process.env.NEXT_PUBLIC_REPORT_V2_SUCCESS,
    },
    search,
  );
}
