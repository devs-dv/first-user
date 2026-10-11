"""One first-time visit: open Chrome behind the egress guard, run the visitor agent, close Chrome."""

import neatlogs

import page_watch
import trace_safety
from browse import run_persona
from browser import close_browser, open_browser
from config import PAGE_READY_TIMEOUT_MS
from egress import summary_span
from first_impression import write_review
from tools import RunContext


# capture_input=False: `recorder` is an object (see browse.run_persona); the plain-text inputs
# are recorded explicitly.
@neatlogs.span(kind="WORKFLOW", name="first_visit", capture_input=False)
async def first_visit(
    url: str,
    goal: str,
    run_id: str,
    recorder=None,
    start_url: str | None = None,
    credentials=None,
    test_login_unavailable: bool = False,
    access_mode: str = "signup",
    access_mode_chosen: bool = True,
) -> dict:
    """Everything a visit does, background work included, finishes inside this root span.

    `start_url` is a page past the login the founder gave; the visit begins there. `credentials`
    is their throwaway test login (credentials.TestCredentials); it is only typed into the page
    being tested. `test_login_unavailable` means a login was provided but could not be loaded.
    `access_mode` is how the founder let the visitor in: "public", "link", "account" or "signup".
    """
    # Only plain values are recorded as the span's input: `credentials` and `recorder` are objects.
    trace_safety.set_input(url=url, goal=goal, run_id=run_id, start_url=start_url, access_mode=access_mode,
                           test_login=bool(credentials) or test_login_unavailable)
    if credentials is not None:
        # From here, the values are redacted in every span and scrubbed from every tool result.
        credentials.register()
    trace_id = current_trace_id()
    browser, stagehand, page, guard = await open_browser()
    try:
        await page_watch.install(page)
        ctx = RunContext(
            url=url, goal=goal, run_id=run_id, stagehand=stagehand, page=page, recorder=recorder, egress=guard,
            credentials=credentials, start_url=start_url, access_mode=access_mode,
            access_mode_chosen=access_mode_chosen,
        )
        if credentials is not None:
            ctx.entry["test_login"] = "provided_not_used"
        elif test_login_unavailable:
            ctx.entry["test_login"] = "failed"

        # The first impression is always of the public landing page, what a newcomer sees without
        # logging in, so with a start link the visit goes there afterwards.
        await open_start_page(page, url, guard)
        if not guard.blocks:
            await _first_impression(ctx)
        if start_url:
            await open_start_page(page, start_url, guard)
        result = await run_persona(ctx)
    finally:
        # Closes the browser, the guard's connections and the lookup client before the root ends.
        await close_browser(browser, stagehand, guard)
        egress_summary = summary_span(guard.summary())
    return {**result, "egress": egress_summary, "trace_id": trace_id}


async def _first_impression(ctx: RunContext) -> None:
    """Write the review of the landing page and save it at once, so the live page can show it."""
    await _settle(ctx.page)
    ctx.first_impression_tried = True
    ctx.first_impression = await write_review(ctx.url, ctx.page, ctx.usage)
    if ctx.first_impression is not None and ctx.recorder is not None and hasattr(ctx.recorder, "first_impression"):
        try:
            await ctx.recorder.first_impression(ctx.first_impression)
        except Exception as error:
            print(f"[first impression]   !! could not record it: {type(error).__name__}", flush=True)


async def _settle(page, seconds: float = 6.0) -> None:
    """Give a script-rendered page a moment to put something on screen before it is read."""
    waited = 0.0
    while waited < seconds:
        try:
            text_length = await page.evaluate("document.body ? document.body.innerText.trim().length : 0")
            ready = await page.evaluate("document.readyState")
        except Exception:
            return
        if text_length > 80 and ready != "loading":
            break
        await page.wait_for_timeout(500)
        waited += 0.5
    await page.wait_for_timeout(700)


def current_trace_id() -> str | None:
    """The neatlogs trace id of the active span, from its W3C traceparent header."""
    headers: dict[str, str] = {}
    if not neatlogs.inject_trace_context(headers):
        return None
    parts = headers.get("traceparent", "").split("-")
    return parts[1] if len(parts) == 4 else None


async def open_start_page(page, url: str, guard) -> None:
    """Navigate and continue once the DOM is ready, without waiting for the full load event.

    Slow scripts or third-party resources can hold up even DOMContentLoaded (on
    the-internet.herokuapp.com it takes about 35 s in Chrome). After PAGE_READY_TIMEOUT_MS
    the visit goes ahead with whatever has rendered, unless nothing has.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_READY_TIMEOUT_MS)
    except Exception:
        # A refused navigation can surface as a load error; the guard's record says why.
        if guard.blocks:
            return
        if not await _has_rendered(page):
            raise
        print(f"[visit] {url} was not ready after {PAGE_READY_TIMEOUT_MS / 1000:.0f} s; continuing with what "
              "has rendered", flush=True)


async def _has_rendered(page) -> bool:
    try:
        return (await page.url()).startswith(("http://", "https://")) and bool(
            await page.evaluate("document.body ? document.body.innerText.trim().length > 0 : false")
        )
    except Exception:
        return False
