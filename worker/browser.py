import os

from stagehand import Stagehand, local_browser

from config import DEVICE_SCALE_FACTOR, LOOKUP_MODEL


async def open_browser():
    """Launch a local Chrome window and attach Stagehand to it."""
    browser = await local_browser.launch(headless=False, device_scale_factor=DEVICE_SCALE_FACTOR)
    try:
        stagehand = await Stagehand.create(
            browser=browser,
            model=LOOKUP_MODEL,
            model_api_key=os.environ["ANTHROPIC_API_KEY"],
        )
    except BaseException:
        await browser.close()
        raise
    page = (await browser.context.pages())[0]
    return browser, stagehand, page


async def close_browser(browser, stagehand):
    """Close Stagehand before the browser, as the Stagehand docs require."""
    try:
        await stagehand.close()
    finally:
        await browser.close()
