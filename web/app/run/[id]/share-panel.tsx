"use client";

// Share this report: copy the link, or post it on X or LinkedIn with an editable default text.

import { useState } from "react";

import { shareLinks, shareText, siteName } from "@/lib/report-view";
import type { VerdictKind } from "@/lib/types";

import { copyText } from "../../copy";

export function SharePanel({ url, kind }: { url: string; kind: VerdictKind }) {
  // The link is this page's address without any query (such as ?report=basic). The report renders only
  // after the run is fetched in the browser, so reading the address here cannot differ from a server render.
  const [link] = useState(() => (typeof window === "undefined" ? "" : `${window.location.origin}${window.location.pathname}`));
  const [message, setMessage] = useState(() => shareText(siteName(url), link, kind));
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");

  const links = shareLinks(message);

  async function copy() {
    setCopied((await copyText(link)) ? "copied" : "failed");
    setTimeout(() => setCopied("idle"), 1600);
  }

  return (
    <section aria-labelledby="share-title" className="flex flex-col gap-3.5 border-t border-line pt-6">
      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <h2 id="share-title" className="m-0 text-[17px] font-semibold">
          Share this report
        </h2>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={copy} disabled={!link} className="fu-btn fu-btn-ghost">
            <span aria-live="polite">{copied === "copied" ? "Link copied ✓" : copied === "failed" ? "Couldn't copy" : "Copy link"}</span>
          </button>
          <a href={links.x} target="_blank" rel="noopener noreferrer" className="fu-btn fu-btn-ghost">
            Share on X
          </a>
          <a href={links.linkedin} target="_blank" rel="noopener noreferrer" className="fu-btn fu-btn-ghost">
            Share on LinkedIn
          </a>
        </div>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="fu-eyebrow-sm">Post text · edit before sharing</span>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={3}
          maxLength={600}
          className="w-full resize-y rounded-field border-[1.5px] border-line bg-s1 px-3.5 py-3 text-[15px] leading-normal outline-none focus:border-ink"
        />
      </label>
    </section>
  );
}
