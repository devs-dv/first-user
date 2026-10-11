"""Record errors the page hits while an action runs: JS errors, console errors, failed requests.

Stagehand's Python page API reports console messages only, so the recording happens
inside the page: a small script, installed on every new document and injected into
the current one, logs uncaught errors, unhandled promise rejections, console.error
calls, fetch/XHR responses with status 4xx or 5xx (or a network error), and
resources (scripts, images, styles) that fail to load. Each entry carries a
timestamp, so an action collects only what happened after it started.
"""

import json
from urllib.parse import urlsplit

MAX_ITEMS = 5
MAX_ITEM_CHARS = 160

WATCH_JS = r"""(() => {
  if (window.__firstUserWatch) return;
  const log = window.__firstUserWatch = [];
  const push = (kind, text) => {
    if (log.length < 100) log.push({kind, text: String(text).slice(0, 300), t: Date.now()});
  };
  addEventListener('error', (event) => {
    const el = event.target;
    if (el && el !== window && (el.src || el.href)) push('request', 'failed to load ' + (el.src || el.href));
    else push('js_error', event.message || 'error');
  }, true);
  addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    push('js_error', 'unhandled rejection: ' + ((reason && reason.message) || reason));
  });
  const consoleError = console.error;
  console.error = function (...args) {
    push('console_error', args.map((a) => (a && a.message) || String(a)).join(' '));
    return consoleError.apply(this, args);
  };
  const originalFetch = window.fetch;
  if (originalFetch) {
    window.fetch = async function (...args) {
      const url = (args[0] && args[0].url) || String(args[0]);
      try {
        const response = await originalFetch.apply(this, args);
        if (response.status >= 400) push('request', response.status + ' ' + (response.url || url));
        return response;
      } catch (error) {
        push('request', 'network error ' + url);
        throw error;
      }
    };
  }
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__firstUserUrl = String(url);
    return open.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener('load', () => {
      if (this.status >= 400) push('request', this.status + ' ' + this.__firstUserUrl);
    });
    this.addEventListener('error', () => push('request', 'network error ' + this.__firstUserUrl));
    return send.apply(this, args);
  };
})();"""


async def install(page) -> None:
    """Install the recorder for every future document, and in the current one."""
    await page.add_init_script(WATCH_JS)
    await inject(page)


async def inject(page) -> None:
    try:
        await page.evaluate(WATCH_JS)
    except Exception:
        pass  # a page that is still loading gets the init script instead


async def now(page) -> float:
    """The page's clock, so entries from a page that navigated mid-action still compare."""
    await inject(page)
    try:
        return float(await page.evaluate("Date.now()"))
    except Exception:
        return 0.0


async def collect(page, since: float) -> list[str]:
    """Short descriptions of the errors recorded since `since`, own-site requests only.

    Failed requests to other sites (analytics, ads) and the browser's opaque "Script error."
    for cross-origin scripts are left out, because they say nothing about this site.
    """
    try:
        entries = json.loads(await page.evaluate("JSON.stringify(window.__firstUserWatch || [])"))
        site = _site(await page.url())
    except Exception:
        return []
    seen, items = set(), []
    for entry in entries:
        if entry["t"] < since:
            continue
        text = entry["text"]
        if entry["kind"] == "request" and site and not _same_site(text, site):
            continue
        if text.strip() in ("Script error.", ""):
            continue
        item = f"{entry['kind']}: {text}"[:MAX_ITEM_CHARS]
        if item not in seen:
            seen.add(item)
            items.append(item)
    return items[:MAX_ITEMS]


def _site(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return ".".join(host.split(".")[-2:])


def _same_site(text: str, site: str) -> bool:
    for word in text.split():
        if word.startswith(("http://", "https://")):
            return _site(word) == site
    return True  # a relative URL is the page's own site
