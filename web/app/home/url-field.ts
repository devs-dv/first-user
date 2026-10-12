// Paste and blur handlers for the address fields that show a fixed "https://" in front (lib/url-input.ts).
// A paste that needs no cleaning is left to the browser, so its undo still works.

import type { ClipboardEvent, FocusEvent } from "react";

import { cleanUrlInput, valueAfterPaste } from "@/lib/url-input";

export function urlFieldHandlers(set: (value: string, input: HTMLInputElement) => void) {
  return {
    onPaste(event: ClipboardEvent<HTMLInputElement>) {
      const input = event.currentTarget;
      const pasted = event.clipboardData.getData("text");
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? start;
      const cleaned = valueAfterPaste(input.value, pasted, start, end);
      if (cleaned === input.value.slice(0, start) + pasted + input.value.slice(end)) return;
      event.preventDefault();
      set(cleaned, input);
    },
    onBlur(event: FocusEvent<HTMLInputElement>) {
      const input = event.currentTarget;
      const cleaned = cleanUrlInput(input.value);
      if (cleaned !== input.value) set(cleaned, input);
    },
  };
}
