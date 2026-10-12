import { safeHref } from "@/lib/brief-logic";

export function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.host + (parsed.pathname === "/" ? "" : parsed.pathname);
  } catch {
    return url;
  }
}

// Only http(s) addresses become links: a page's own text never gets to write a javascript: link.
export function SourceLink({ url, label }: { url: string; label?: string }) {
  const href = safeHref(url);
  const text = label ?? displayUrl(url);
  if (!href) return <span className="break-all text-subtle">{text}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="break-all text-accent hover:underline">
      {text}
    </a>
  );
}
