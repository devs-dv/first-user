import { HIDDEN_TEXT_NOTICE, type HiddenTextNote } from "@/lib/brief-types";

// One fixed sentence, written by the worker's code and repeated here, and where it was found (a page address and
// how it was hidden). The hidden text itself is never kept or shown.
export function HiddenTextNotice({ note }: { note: HiddenTextNote }) {
  const places = note.found.map((item) => `${item.url} (${item.method.replace(/_/g, " ")})`);
  return (
    <section role="note" className="rounded-xl border border-warning/40 bg-surface p-4 text-sm">
      <p className="font-medium">{HIDDEN_TEXT_NOTICE}</p>
      <p className="mt-1 text-muted">Found on: {places.join("; ")}</p>
    </section>
  );
}
