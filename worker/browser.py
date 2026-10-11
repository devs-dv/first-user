import os
import socket

from stagehand import Stagehand, local_browser

import lookup_model
from config import DEVICE_SCALE_FACTOR, LOOKUP_MODEL, LOOKUP_VIA
from egress import CHROME_EXTRA_ARGS, CHROME_PROXY_BYPASS, EgressGuard


async def open_browser():
    """Start the egress guard, launch a local Chrome window behind it and attach Stagehand.

    Every request Chrome makes goes through the guard, which refuses private,
    loopback, link-local and cloud-metadata addresses (see egress.py).
    """
    guard = EgressGuard()
    await guard.start()
    guard.devtools_port = _free_port()
    try:
        browser = await local_browser.launch(
            headless=False,
            port=guard.devtools_port,
            device_scale_factor=DEVICE_SCALE_FACTOR,
            proxy_server=guard.proxy_server,
            proxy_bypass=CHROME_PROXY_BYPASS,
            args=CHROME_EXTRA_ARGS,
        )
    except BaseException:
        await guard.close()
        raise
    try:
        if LOOKUP_VIA == "callback":
            stagehand = await Stagehand.create(browser=browser, model=lookup_model.generate)
        else:
            stagehand = await Stagehand.create(
                browser=browser,
                model=LOOKUP_MODEL,
                model_api_key=os.environ["ANTHROPIC_API_KEY"],
            )
    except BaseException:
        try:
            await browser.close()
        finally:
            await guard.close()
        raise
    page = (await browser.context.pages())[0]
    return browser, stagehand, page, guard


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def close_browser(browser, stagehand, guard):
    """Close Stagehand before the browser, as the Stagehand docs require, then the guard
    and the lookup model's client."""
    try:
        await stagehand.close()
    finally:
        try:
            await browser.close()
        finally:
            try:
                await guard.close()
            finally:
                await lookup_model.close()
