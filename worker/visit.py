"""One first-time visit: open Chrome behind the egress guard, run the visitor agent, close Chrome."""

import neatlogs

from browse import run_persona
from browser import close_browser, open_browser
from tools import RunContext


@neatlogs.span(kind="WORKFLOW", name="first_visit")
async def first_visit(url: str, goal: str, run_id: str, recorder=None) -> dict:
    browser, stagehand, page, guard = await open_browser()
    try:
        try:
            await page.goto(url)
        except Exception:
            # A refused navigation can surface as a load error; the guard's record says why.
            if not guard.blocks:
                raise
        ctx = RunContext(
            url=url, goal=goal, run_id=run_id, stagehand=stagehand, page=page, recorder=recorder, egress=guard
        )
        return await run_persona(ctx)
    finally:
        await close_browser(browser, stagehand, guard)
