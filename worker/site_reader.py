"""Bounded discovery of one website's pages, for "Understand this website".

Reads the homepage and then a small number of same-site pages chosen by link text and path (about,
product, features, pricing, docs, FAQ, customers, blog index). Every request goes through the egress
guard (egress.py), so private, loopback, link-local and metadata addresses are refused here exactly as
they are in the browser, and each redirect hop is vetted the same way.

Politeness and limits, all in one place:

  robots.txt   honoured, with the Crawl-delay if there is one (capped)
  delay        a wait between requests to the site
  pages        at most MAX_PAGES in all (the homepage and the pages chosen from it)
  bytes        at most MAX_PAGE_BYTES read from one page
  time         at most MAX_SECONDS for the whole read
  browser      only for a page whose text is too thin without JavaScript, at most MAX_RENDERS times

The model never sees this module: it gets the pages it returns (understand.py).
"""

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import neatlogs

import trace_safety
from egress import EgressGuard

USER_AGENT = "FirstUserBot/1.0 (reads a few public pages to write a product brief)"
MAX_PAGES = int(os.environ.get("UNDERSTAND_MAX_PAGES", "9"))  # the homepage plus 8
MAX_PAGE_BYTES = int(os.environ.get("UNDERSTAND_MAX_PAGE_BYTES", str(600_000)))
MAX_SECONDS = float(os.environ.get("UNDERSTAND_MAX_SECONDS", "120"))
REQUEST_DELAY_SECONDS = float(os.environ.get("UNDERSTAND_DELAY_SECONDS", "1.0"))
MAX_CRAWL_DELAY_SECONDS = 5.0
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_REDIRECTS = 4
# Below this many characters of visible text a page is probably drawn by JavaScript.
THIN_TEXT_CHARS = 400
MAX_RENDERS = 3
MAX_TEXT_CHARS = 20_000  # kept per page; the model is given less (understand.py)

# Link kinds in the order they are worth reading. Each is (kind, words in the link text, words in the path).
KINDS: list[tuple[str, re.Pattern, re.Pattern]] = [
    ("pricing", re.compile(r"\b(pricing|prices?|plans?|plans? (&|and) pricing)\b", re.I),
     re.compile(r"(^|/)(pricing|prices?|plans?)(/|$|-)", re.I)),
    ("product", re.compile(r"\b(product|platform|solutions?|how it works|overview|use cases?|tour)\b", re.I),
     re.compile(r"(^|/)(products?|platform|solutions?|how-it-works|overview|use-cases?|tour)(/|$|-)", re.I)),
    ("features", re.compile(r"\b(features?|capabilities)\b", re.I),
     re.compile(r"(^|/)(features?|capabilities)(/|$|-)", re.I)),
    ("about", re.compile(r"\b(about|about us|our story|company|mission|who we are)\b", re.I),
     re.compile(r"(^|/)(about|about-us|company|our-story|mission|who-we-are)(/|$|-)", re.I)),
    ("docs", re.compile(r"\b(docs?|documentation|developers?|api|guides?|help cent(er|re))\b", re.I),
     re.compile(r"(^|/)(docs?|documentation|developers?|api|guides?|help)(/|$|-)", re.I)),
    ("faq", re.compile(r"\b(faqs?|frequently asked|questions)\b", re.I),
     re.compile(r"(^|/)(faqs?|questions)(/|$|-)", re.I)),
    ("customers", re.compile(r"\b(customers?|case stud(y|ies)|stories|success stories|testimonials)\b", re.I),
     re.compile(r"(^|/)(customers?|case-stud(y|ies)|stories|success-stories|testimonials)(/|$|-)", re.I)),
    ("blog", re.compile(r"\b(blog|news)\b", re.I), re.compile(r"(^|/)(blog|news)(/|$)", re.I)),
]
KIND_ORDER = [kind for kind, _, _ in KINDS]
# Pages a visitor reads to understand a product never need these.
NOT_WANTED_PATH = re.compile(
    r"(^|/)(login|log-in|signin|sign-in|signup|sign-up|register|account|cart|checkout|privacy|terms|legal|"
    r"cookies?|careers?|jobs|press|contact|unsubscribe|cdn-cgi|wp-admin|wp-login|feed|rss|sitemap|changelog|releases?|release-notes|status)(/|$|\.|-)", re.I)
NOT_HTML_PATH = re.compile(
    r"\.(pdf|png|jpe?g|gif|webp|svg|ico|zip|gz|mp4|mov|mp3|css|js|json|xml|txt|csv|docx?|xlsx?|pptx?|woff2?)$", re.I)


# ----------------------------------------------------------------------------------- parsing HTML
_SKIPPED = {"script", "style", "noscript", "template", "svg", "head", "iframe", "canvas"}
_BLOCKS = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer", "main",
           "nav", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "form", "dt", "dd", "hr"}


@dataclass
class ParsedPage:
    title: str = ""
    description: str = ""
    headings: list[str] = field(default_factory=list)
    text: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (absolute url, link text)


class _Extractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.description = ""
        self.headings: list[str] = []
        self.chunks: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip_depth = 0
        self._in_title = False
        self._heading: list[str] | None = None
        self._link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag, attrs):
        attributes = {name: value or "" for name, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (attributes.get("name") or attributes.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = attributes.get("content", "")
        if tag == "body":
            self._skip_depth = 0  # a head that was never closed must not hide the page
        if tag in _SKIPPED:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _BLOCKS:
            self.chunks.append("\n")
        if tag in ("h1", "h2", "h3"):
            self._heading = []
        if tag == "a" and attributes.get("href"):
            self._link = (attributes["href"], [attributes.get("aria-label", "")])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _SKIPPED:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _BLOCKS:
            self.chunks.append("\n")
        if tag in ("h1", "h2", "h3") and self._heading is not None:
            heading = " ".join("".join(self._heading).split())
            if heading:
                self.headings.append(heading)
            self._heading = None
        if tag == "a" and self._link is not None:
            href, parts = self._link
            self._link = None
            text = " ".join(" ".join(parts).split())
            try:
                self.links.append((urljoin(self.base_url, href), text))
            except ValueError:
                pass

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._skip_depth:
            return
        self.chunks.append(data)
        if self._heading is not None:
            self._heading.append(data)
        if self._link is not None:
            self._link[1].append(data)


def parse_html(html: str, base_url: str) -> ParsedPage:
    """Title, description, headings, visible text and links of an HTML page. Never raises."""
    extractor = _Extractor(base_url)
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        pass  # keep whatever was read before the markup broke
    lines, seen = [], set()
    for raw in "".join(extractor.chunks).split("\n"):
        line = " ".join(raw.split())
        if not line:
            continue
        # A menu repeated in the header and footer is read once.
        if len(line) < 80:
            if line in seen:
                continue
            seen.add(line)
        lines.append(line)
    return ParsedPage(
        title=" ".join("".join(extractor.title_parts).split())[:200],
        description=" ".join(extractor.description.split())[:400],
        headings=extractor.headings[:30],
        text="\n".join(lines)[:MAX_TEXT_CHARS],
        links=extractor.links,
    )


# ----------------------------------------------------------------------------------- choosing pages
def _site_key(url: str) -> tuple[str, int | None]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    default = 443 if parts.scheme == "https" else 80
    port = parts.port if parts.port not in (None, default) else None
    return host, port


def same_site(url: str, home_url: str) -> bool:
    """True for the homepage's host (with or without www) and its subdomains, on the same port."""
    host, port = _site_key(url)
    home_host, home_port = _site_key(home_url)
    if not host or not home_host or port != home_port:
        return False
    return host == home_host or host.endswith("." + home_host)


def normalise(url: str) -> str | None:
    """An http(s) URL without a fragment or query, or None for anything else (mailto:, tel:, javascript:)."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))


def classify_link(url: str, text: str) -> tuple[str, int] | None:
    """The kind of page a link probably leads to and a score (higher is better), or None.

    The path counts for more than the link text. A blog counts only as its index, not a post.
    """
    path = urlsplit(url).path
    if NOT_WANTED_PATH.search(path) or NOT_HTML_PATH.search(path):
        return None
    depth = len([segment for segment in path.split("/") if segment])
    best: tuple[str, int] | None = None
    for kind, text_pattern, path_pattern in KINDS:
        score = 0
        if path_pattern.search(path):
            score += 3
        if text and len(text) <= 60 and text_pattern.search(text):
            score += 2
        if score == 0:
            continue
        if kind == "blog" and depth > 1:
            continue
        score -= max(0, depth - 1)  # shallow paths are the section's own page
        if best is None or score > best[1]:
            best = (kind, score)
    return best


def choose_pages(home_url: str, links: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    """Up to `limit` same-site pages as (url, kind): the best link of each kind first, then the next best
    of each, in the order of KIND_ORDER. The homepage itself is never chosen."""
    home = normalise(home_url)
    by_kind: dict[str, list[tuple[int, int, str]]] = {kind: [] for kind in KIND_ORDER}
    seen: set[str] = set()
    for order, (raw, text) in enumerate(links):
        url = normalise(raw)
        if url is None or url in seen or url == home or not same_site(url, home_url):
            continue
        seen.add(url)
        classified = classify_link(url, text)
        if classified is not None:
            kind, score = classified
            by_kind[kind].append((-score, order, url))
    for candidates in by_kind.values():
        candidates.sort()
    chosen: list[tuple[str, str]] = []
    rank = 0
    while len(chosen) < limit and any(len(c) > rank for c in by_kind.values()):
        for kind in KIND_ORDER:
            if len(chosen) >= limit:
                break
            if len(by_kind[kind]) > rank:
                chosen.append((by_kind[kind][rank][2], kind))
        rank += 1
    return chosen


# ----------------------------------------------------------------------------------- fetching
class SiteRefused(Exception):
    """The egress guard refused an address; the message is safe to show the visitor."""


@dataclass
class Fetched:
    url: str  # the final address, after redirects
    status: int
    content_type: str
    body: bytes
    truncated: bool = False


@dataclass
class PageRead:
    url: str
    kind: str  # home | pricing | product | ...
    title: str
    description: str
    headings: list[str]
    text: str
    method: str  # "http" or "browser"
    status: int
    bytes: int
    links: list[tuple[str, str]] = field(default_factory=list)

    def meta(self) -> dict:
        """What the trace and the brief keep about a page: never its text."""
        return {"url": self.url, "kind": self.kind, "title": self.title, "method": self.method,
                "status": self.status, "bytes": self.bytes, "text_chars": len(self.text)}


@dataclass
class SiteRead:
    pages: list[PageRead] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # {"url", "kind", "reason"}
    seconds: float = 0.0
    renders: int = 0
    stopped: str | None = None  # why discovery ended early, if it did


class BrowserRenderer:
    """The worker's own browser (behind its own egress guard), opened on first use and only for pages
    that need JavaScript to show their text."""

    def __init__(self):
        self._opened = None

    async def render(self, url: str) -> str:
        """The page's HTML after scripts ran. Raises SiteRefused if the browser's guard refused something."""
        if self._opened is None:
            from browser import open_browser

            self._opened = await open_browser()
        _, _, page, guard = self._opened
        from visit import _settle, open_start_page

        await open_start_page(page, url, guard)
        if guard.blocks:
            raise SiteRefused(guard.block_reason() or "The browser refused an address.")
        await _settle(page)
        return await page.evaluate("document.documentElement.outerHTML")

    async def close(self) -> None:
        if self._opened is not None:
            from browser import close_browser

            browser, stagehand, _, guard = self._opened
            self._opened = None
            await close_browser(browser, stagehand, guard)


class SiteReader:
    """GET through the egress guard, politely."""

    def __init__(self, guard: EgressGuard, *, delay: float = REQUEST_DELAY_SECONDS, max_bytes: int = MAX_PAGE_BYTES,
                 sleep=asyncio.sleep, clock=time.monotonic):
        self.guard, self.delay, self.max_bytes, self.sleep, self.clock = guard, delay, max_bytes, sleep, clock
        self.crawl_delay: float | None = None
        self._last_request: float | None = None
        self._client = httpx.AsyncClient(
            proxy=guard.proxy_server, follow_redirects=False, trust_env=False, timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                     "Accept-Language": "en"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _wait_turn(self) -> None:
        """Be polite: leave a gap after the previous request to the site."""
        gap = max(self.delay, min(self.crawl_delay or 0.0, MAX_CRAWL_DELAY_SECONDS))
        if self._last_request is not None and gap > 0:
            remaining = gap - (self.clock() - self._last_request)
            if remaining > 0:
                await self.sleep(remaining)
        self._last_request = self.clock()

    async def get(self, url: str, *, home_url: str | None = None, first: bool = False) -> Fetched:
        """GET `url` through the guard, following up to MAX_REDIRECTS redirects by hand.

        After the first page, a redirect off the site is not followed. Raises SiteRefused when the guard
        refused an address, httpx.HTTPError for network failures.
        """
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await self._wait_turn()
            blocks_before = len(self.guard.blocks)
            try:
                async with self._client.stream("GET", current) as response:
                    if len(self.guard.blocks) > blocks_before:
                        raise SiteRefused(self.guard.block_reason())
                    if response.is_redirect and response.headers.get("location"):
                        target = normalise(urljoin(current, response.headers["location"]))
                        if target is None:
                            raise httpx.HTTPError("redirect to something that is not a web page")
                        if not first and home_url and not same_site(target, home_url):
                            return Fetched(current, response.status_code, "", b"")
                        current = target
                        continue
                    body = bytearray()
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= self.max_bytes:
                            del body[self.max_bytes:]
                            truncated = True
                            break
                    return Fetched(str(response.url), response.status_code,
                                   response.headers.get("content-type", ""), bytes(body), truncated)
            except httpx.HTTPError:
                # A refusal over https is a refused CONNECT, which the client reports as a proxy error.
                if len(self.guard.blocks) > blocks_before:
                    raise SiteRefused(self.guard.block_reason()) from None
                raise
        raise httpx.HTTPError("too many redirects")


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    for encoding in ([match.group(1)] if match else []) + ["utf-8"]:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def _is_html(content_type: str) -> bool:
    return not content_type or "html" in content_type.lower()


@neatlogs.span(kind="TOOL", name="fetch_page", capture_input=False)
async def fetch_page(discovery: "SiteDiscovery", url: str, kind: str) -> dict:
    """One page of the site, as its own span. The trace gets the page's facts, never its text; the page
    itself is left on the discovery for the caller."""
    trace_safety.set_input(url=url, kind=kind)
    discovery.last = await discovery.read_one(url, kind)
    if discovery.last is not None:
        return discovery.last.meta()
    return {"url": url, "kind": kind, "read": False,
            "reason": discovery.skipped[-1]["reason"] if discovery.skipped else ""}


class SiteDiscovery:
    """Reads the homepage and the pages chosen from it, inside the limits at the top of this file."""

    def __init__(self, home_url: str, guard: EgressGuard, *, renderer=None, delay: float = REQUEST_DELAY_SECONDS,
                 max_pages: int = MAX_PAGES, max_bytes: int = MAX_PAGE_BYTES, max_seconds: float = MAX_SECONDS,
                 sleep=asyncio.sleep, clock=time.monotonic):
        self.home_url = home_url
        self.max_pages, self.max_seconds, self.clock = max_pages, max_seconds, clock
        self.reader = SiteReader(guard, delay=delay, max_bytes=max_bytes, sleep=sleep, clock=clock)
        self.renderer = renderer
        self.robots: robotparser.RobotFileParser | None = None
        self.result = SiteRead()
        self.skipped = self.result.skipped
        self.last: PageRead | None = None
        self._started = clock()

    @property
    def seconds_left(self) -> float:
        return self.max_seconds - (self.clock() - self._started)

    async def _load_robots(self, url: str) -> None:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        parser = robotparser.RobotFileParser()
        try:
            fetched = await self.reader.get(robots_url, home_url=self.home_url, first=False)
        except httpx.HTTPError:
            parser.parse([])  # not reachable: nothing is asked of us
            self.robots = parser
            return
        if fetched.status >= 500:
            parser.parse(["User-agent: *", "Disallow: /"])  # the site is struggling: stay away
        elif fetched.status >= 400 or not fetched.body:
            parser.parse([])
        else:
            parser.parse(_decode(fetched.body, fetched.content_type).splitlines())
        delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*")
        self.reader.crawl_delay = float(delay) if delay else None
        self.robots = parser

    def _allowed(self, url: str) -> bool:
        return self.robots is None or self.robots.can_fetch(USER_AGENT, url)

    async def read_one(self, url: str, kind: str) -> PageRead | None:
        """Fetch and parse one page, or record why it was skipped and return None."""
        def skip(reason: str) -> None:
            self.skipped.append({"url": url, "kind": kind, "reason": reason})

        if not self._allowed(url):
            skip("robots.txt asks automated visitors not to read this page")
            return None
        try:
            fetched = await asyncio.wait_for(
                self.reader.get(url, home_url=self.home_url, first=kind == "home"), max(1.0, self.seconds_left))
        except SiteRefused as refusal:
            self.result.stopped = str(refusal)
            skip("refused: a private, local or cloud-metadata address")
            return None
        except (httpx.HTTPError, asyncio.TimeoutError) as error:
            skip(f"could not be fetched ({type(error).__name__})")
            return None
        if fetched.status >= 400 or not fetched.body:
            skip(f"the site answered {fetched.status}" if fetched.status else "no content")
            return None
        if not _is_html(fetched.content_type):
            skip(f"not a web page ({fetched.content_type.split(';')[0]})")
            return None

        method = "http"
        parsed = parse_html(_decode(fetched.body, fetched.content_type), fetched.url)
        if (len(parsed.text) < THIN_TEXT_CHARS and self.renderer is not None
                and self.result.renders < MAX_RENDERS and self.seconds_left > 10):
            self.result.renders += 1
            try:
                rendered = await asyncio.wait_for(self.renderer.render(fetched.url), max(5.0, self.seconds_left))
                again = parse_html(rendered, fetched.url)
                if len(again.text) > len(parsed.text):
                    parsed, method = again, "browser"
            except SiteRefused as refusal:
                self.result.stopped = str(refusal)
            except Exception as error:  # a render that fails leaves the page as the plain fetch saw it
                print(f"[understand] browser read of {fetched.url} failed: {type(error).__name__}", flush=True)
        return PageRead(
            url=fetched.url, kind=kind, title=parsed.title, description=parsed.description, headings=parsed.headings,
            text=parsed.text, method=method, status=fetched.status, bytes=len(fetched.body), links=parsed.links,
        )

    async def run(self) -> SiteRead:
        """Homepage first, then the best pages from its links, never more than max_pages in all."""
        try:
            try:
                await self._load_robots(self.home_url)
            except SiteRefused as refusal:
                self.result.stopped = str(refusal)
                return self._finish()
            await fetch_page(self, self.home_url, "home")
            home = self.last
            if home is None:
                return self._finish()
            self.result.pages.append(home)
            if not same_site(home.url, self.home_url):
                # The homepage moved to another address (example.com to example.io): the site is that one now.
                self.home_url = home.url
                try:
                    await self._load_robots(home.url)
                except SiteRefused as refusal:
                    self.result.stopped = str(refusal)
                    return self._finish()
            for url, kind in choose_pages(self.home_url, home.links, self.max_pages - 1):
                if len(self.result.pages) >= self.max_pages or self.result.stopped:
                    break
                if self.seconds_left <= 0:
                    self.skipped.append({"url": url, "kind": kind, "reason": "the time limit was reached"})
                    continue
                await fetch_page(self, url, kind)
                if self.last is not None and all(page.url != self.last.url for page in self.result.pages):
                    self.result.pages.append(self.last)
            return self._finish()
        finally:
            await self.reader.close()
            if self.renderer is not None:
                await self.renderer.close()

    def _finish(self) -> SiteRead:
        self.result.seconds = round(self.clock() - self._started, 2)
        return self.result
