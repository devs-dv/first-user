"""One first-time visit: open Chrome, run the visitor agent, close Chrome."""

import neatlogs

from browse import run_persona
from browser import close_browser, open_browser
from tools import RunContext


@neatlogs.span(kind="WORKFLOW", name="first_visit")
async def first_visit(url: str, goal: str, run_id: str, recorder=None) -> dict:
    browser, stagehand, page = await open_browser()
    try:
        await page.goto(url)
        ctx = RunContext(url=url, goal=goal, run_id=run_id, stagehand=stagehand, page=page, recorder=recorder)
        return await run_persona(ctx)
    finally:
        await close_browser(browser, stagehand)
