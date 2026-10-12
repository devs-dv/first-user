"use client";

// State the home page's separate pieces share: the address typed in the hero (the form uses the same
// one), the form's tab, and the step of the hero's demo run, which also lights up "How it works".

import { useEffect, useSyncExternalStore } from "react";

import { reducedMotion } from "../motion";
import { HERO_RUN } from "./data";

export type Tab = "test" | "understand";
type HomeState = { url: string; tab: Tab; step: number };

const INITIAL: HomeState = { url: "", tab: "test", step: 0 };
// With reduced motion the demo run stands still on its "goal reached" step, as in the design.
const STILL_STEP = 6;

let state: HomeState = INITIAL;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setHome(patch: Partial<HomeState>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

export function useHome<T>(select: (s: HomeState) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => select(state),
    () => select(INITIAL),
  );
}

// Started once by the hero: one step of the demo run every two seconds.
export function useHeroClock() {
  useEffect(() => {
    if (reducedMotion()) {
      setHome({ step: STILL_STEP });
      return;
    }
    const timer = setInterval(() => setHome({ step: (state.step + 1) % HERO_RUN.length }), 2000);
    return () => clearInterval(timer);
  }, []);
}
