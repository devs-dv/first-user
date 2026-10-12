"use client";

import { useEffect } from "react";

import { RELOAD_KEY, isChunkLoadError, isOwnAssetUrl, mayReload } from "@/lib/version-skew";

// Reloads the page once when a piece of the app's code fails to load (lib/version-skew.ts): after a redeploy,
// an open tab otherwise stays stuck until a hard refresh. At most once a minute; without sessionStorage there
// is no way to keep count, so it never reloads.
export function VersionGuard() {
  useEffect(() => {
    function reloadOnce() {
      try {
        if (!mayReload(sessionStorage.getItem(RELOAD_KEY), Date.now())) return;
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
      } catch {
        return;
      }
      window.location.reload();
    }
    function onError(event: ErrorEvent | Event) {
      const target = event.target as HTMLScriptElement | HTMLLinkElement | null;
      if (target && (target instanceof HTMLScriptElement || target instanceof HTMLLinkElement)) {
        if (isOwnAssetUrl(target instanceof HTMLScriptElement ? target.src : target.href)) reloadOnce();
        return;
      }
      if (isChunkLoadError((event as ErrorEvent).error ?? (event as ErrorEvent).message)) reloadOnce();
    }
    function onRejection(event: PromiseRejectionEvent) {
      if (isChunkLoadError(event.reason)) reloadOnce();
    }
    // Capture: a <script> or <link> that fails to load does not bubble.
    window.addEventListener("error", onError, true);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError, true);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  return null;
}
