import { safeHref } from "@/lib/brief-logic";

export function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.host + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url;
  }
}

// The page part of a source address ("/pricing"), or the host for the homepage.
export function sourceLabel(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.pathname === "/" ? `${parsed.host}/` : parsed.pathname;
  } catch {
    return url;
  }
}

// Only http(s) addresses become links: a page's own text never gets to write a javascript: link.
export function SourceLink({ url, label }: { url: string; label?: string }) {
  const href = safeHref(url);
  const text = label ?? sourceLabel(url);
  const className = "font-code text-[12px] font-medium text-ink3 [overflow-wrap:anywhere]";
  if (!href) return <span className={className}>{text}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className={`${className} fu-link hover:text-ink`}>
      {text} ↗
    </a>
  );
}
