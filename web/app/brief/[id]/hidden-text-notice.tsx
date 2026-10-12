import { HIDDEN_TEXT_NOTICE, type HiddenTextNote } from "@/lib/brief-types";
import { methodLabels } from "@/lib/hidden-text";

// The page part of an address ("/review.html"); the evidence holds addresses without query or fragment.
function pagePath(url: unknown): string | null {
  if (typeof url !== "string") return null;
  try {
    return new URL(url).pathname;
  } catch {
    return null;
  }
}

// One small muted line near the top of a brief when a page read for it held text hidden from people and addressed
// to automated agents (stripped before any model read the page). The sentence is the page's own fixed copy of the
// worker's notice; the hiding methods are fixed labels and the pages are only their paths. The hidden text itself
// is never kept or shown.
export function HiddenTextNotice({ note }: { note: HiddenTextNote }) {
  const methods = methodLabels(note.found);
  const pages = [...new Set(note.found.map((item) => pagePath(item.url)).filter((path): path is string => !!path))];
  return (
    <p role="note" className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-field border-[1.5px] border-dashed border-ink3 bg-s1 px-4 py-3 text-[14px] leading-normal text-ink2">
      <span className="fu-chip fu-chip-tag border-none bg-s2 text-ink2">Hidden text</span>
      <span className="min-w-0 flex-1">
        {HIDDEN_TEXT_NOTICE}
        {methods.length > 0 && <span className="text-ink3"> Hidden as {methods.join(", ")}.</span>}
        {pages.length > 0 && <span className="text-ink3"> Found on {pages.join(", ")}.</span>}
      </span>
    </p>
  );
}
