import type { CSSProperties } from "react";

// Inline CSS custom properties (`--min`, `--gap`, ...) typed for React's style prop.
export function cssVars(vars: Record<`--${string}`, string | number>, rest: CSSProperties = {}): CSSProperties {
  return { ...(vars as CSSProperties), ...rest };
}

// The responsive grid used across the design: as many columns of at least `min` as fit.
export function grid(min: string, gap = "14px", rest: CSSProperties = {}): CSSProperties {
  return cssVars({ "--min": min, "--gap": gap }, rest);
}
