// The address fields show a fixed "https://" in front, so a pasted or typed full address would read
// "https://https://…". On paste and on blur the field keeps only what comes after the protocol: spaces around it
// and a leading http:// or https:// are dropped, and a "www." straight after that protocol too. A "www." typed
// without a protocol is left alone, and nothing else is ever changed.

const PROTOCOL = /^https?:\/\//i;

export function cleanUrlInput(value: string): string {
  const trimmed = value.trim();
  const protocol = trimmed.match(PROTOCOL);
  if (!protocol) return trimmed;
  return trimmed.slice(protocol[0].length).replace(/^www\./i, "");
}

// The field's value after a paste: the pasted text replaces the selection (or goes in at the caret), then the
// whole value is cleaned. A missing selection (some input types have none) appends at the end.
export function valueAfterPaste(current: string, pasted: string, start: number | null, end: number | null): string {
  const from = start ?? current.length;
  const to = end ?? from;
  return cleanUrlInput(current.slice(0, from) + pasted + current.slice(to));
}
