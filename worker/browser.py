import os
import shutil
import socket

from stagehand import Stagehand, local_browser

import lookup_model
from config import (
    CHROME_SANDBOX, DEVICE_SCALE_FACTOR, HEADLESS, LOOKUP_MODEL, LOOKUP_VIA, VIEWPORT_HEIGHT, VIEWPORT_WIDTH,
)
from egress import CHROME_EXTRA_ARGS, CHROME_PROXY_BYPASS, EgressGuard

SMALL_SHM_BYTES = 512 * 1024 * 1024


def chrome_args(headless: bool | None = None, shm_path: str = "/dev/shm") -> list[str]:
    """Chrome flags on top of Stagehand's defaults, and why.

    --force-webrtc-ip-handling-policy=disable_non_proxied_udp   (egress.py) WebRTC could open UDP
        connections that skip the egress guard's proxy.
    --disable-gpu                    headless only: a server has no GPU, and this avoids GPU-process
        crashes; pages render in software.
    --disable-dev-shm-usage          only when /dev/shm is under 512 MB: Chrome keeps shared memory
        there and crashes tabs when it is a tiny 64 MB (Docker's default). With --shm-size=1g it is
        not added.
    Stagehand itself adds --headless (HEADLESS), --window-size and --force-device-scale-factor
    (the viewport), --remote-debugging-port, --user-data-dir, --proxy-server / --proxy-bypass-list
    (the egress guard) and --no-sandbox (CHROME_SANDBOX=false, or when running as root).
    """
    args = list(CHROME_EXTRA_ARGS)
    if HEADLESS if headless is None else headless:
        args.append("--disable-gpu")
    try:
        if shutil.disk_usage(shm_path).total < SMALL_SHM_BYTES:
            args.append("--disable-dev-shm-usage")
    except OSError:
        pass  # no /dev/shm (Windows, macOS): nothing to check
    return args


def launch_options(proxy_server: str, port: int) -> dict:
    """The arguments for local_browser.launch(): a fixed viewport, the egress proxy, server flags."""
    return {
        "headless": HEADLESS,
        "port": port,
        "viewport_width": VIEWPORT_WIDTH,
        "viewport_height": VIEWPORT_HEIGHT,
        "device_scale_factor": DEVICE_SCALE_FACTOR,
        "proxy_server": proxy_server,
        "proxy_bypass": CHROME_PROXY_BYPASS,
        "args": chrome_args(),
        # None leaves Stagehand's rule (sandbox on, unless running as root); False adds --no-sandbox.
        "chromium_sandbox": None if CHROME_SANDBOX else False,
    }


async def open_browser():
    """Start the egress guard, launch a local Chrome window behind it and attach Stagehand.

    Every request Chrome makes goes through the guard, which refuses private,
    loopback, link-local and cloud-metadata addresses (see egress.py).
    """
    guard = EgressGuard()
    await guard.start()
    guard.devtools_port = _free_port()
    try:
        browser = await local_browser.launch(**launch_options(guard.proxy_server, guard.devtools_port))
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
    # The window's frame and a laptop's display scaling must not change what a coordinate means:
    # the page is always VIEWPORT_WIDTH x VIEWPORT_HEIGHT at DEVICE_SCALE_FACTOR.
    await page.set_viewport_size(VIEWPORT_WIDTH, VIEWPORT_HEIGHT, device_scale_factor=DEVICE_SCALE_FACTOR)
    return browser, stagehand, page, guard


SANDBOX_HELP = (
    "Chrome did not start with its sandbox on. Usual causes: the container was started without "
    "--security-opt seccomp=./worker/chrome-seccomp.json (Docker's default profile blocks the user "
    "namespaces the sandbox needs); the host restricts unprivileged user namespaces (on Ubuntu 24.04: "
    "sysctl kernel.apparmor_restrict_unprivileged_userns); or CI is set / the process runs as root. "
    "See DEPLOY.md. Only if that cannot be fixed, CHROME_SANDBOX=false starts Chrome without its "
    "sandbox, which lets a hostile page read this process's API keys: a risk to accept knowingly."
)


def sandbox_warnings() -> list[str]:
    """Reasons Chrome will run without its sandbox even though CHROME_SANDBOX is on."""
    reasons = []
    if not CHROME_SANDBOX:
        reasons.append("CHROME_SANDBOX=false: Chrome's sandbox is OFF")
    if os.environ.get("CI"):
        reasons.append("CI is set: Stagehand starts Chrome with --no-sandbox")
    getuid = getattr(os, "getuid", None)
    if getuid is not None and getuid() == 0:
        reasons.append("the worker runs as root: Stagehand starts Chrome with --no-sandbox")
    return reasons


async def browser_preflight() -> tuple[bool, str]:
    """Start the worker's browser once, as a run would, and report whether it works.

    Returns (ok, message). Run at startup, so a host where Chrome cannot start (or only starts
    without its sandbox) is reported at once and not as a failed run later.
    """
    reasons = sandbox_warnings()
    try:
        chrome, stagehand, page, guard = await open_browser()
    except Exception as error:
        detail = f"{type(error).__name__}: {error}"[:300]
        return False, f"The browser could not be started ({detail}). " + SANDBOX_HELP
    try:
        value = await page.evaluate("1 + 1")
        if value != 2:
            return False, f"The browser started but could not run a script (got {value!r})."
    finally:
        await close_browser(chrome, stagehand, guard)
    message = f"browser ok (headless={HEADLESS}, viewport {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT})"
    if reasons:
        message += "; WARNING: " + "; ".join(reasons)
    return True, message


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
        except PermissionError as error:
            # On Windows, Chrome can still hold a cache file while Stagehand deletes its
            # temporary profile. The visit is over by then, so keep its result.
            print(f"[browser] could not remove Chrome's temporary profile: {error}", flush=True)
        finally:
            try:
                await guard.close()
            finally:
                await lookup_model.close()
