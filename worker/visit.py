"""One first-time visit: open Chrome behind the egress guard, run the visitor agent, close Chrome."""

import neatlogs

import page_watch
from browse import run_persona
from browser import close_browser, open_browser
from config import PAGE_READY_TIMEOUT_MS
from tools import RunContext


@neatlogs.span(kind="WORKFLOW", name="first_visit")
async def first_visit(url: str, goal: str, run_id: str, recorder=None) -> dict:
    browser, stagehand, page, guard = await open_browser()
    try:
        await page_watch.install(page)
        await open_start_page(page, url, guard)
        ctx = RunContext(
            url=url, goal=goal, run_id=run_id, stagehand=stagehand, page=page, recorder=recorder, egress=guard
        )
        return await run_persona(ctx)
    finally:
        await close_browser(browser, stagehand, guard)


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
