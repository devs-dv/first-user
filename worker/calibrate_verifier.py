"""Check the verifier's calibration on three hand-built cases, three runs each (real model, ~$0.003).

Usage: python calibrate_verifier.py [case-name-fragment]

Expected: incomplete evidence (no before-state, a thin record) -> unverified, never
contradicted; positive evidence of failure (an error on the page) -> contradicted.
"""
import asyncio
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")
os.environ.pop("NEATLOGS_API_KEY", None)  # no neatlogs export from this script

import verifier  # noqa: E402


def png(width, height, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakePage:
    def __init__(self, url, title, text, color):
        self._url, self._title, self._text, self._png = url, title, text, png(48, 32, color)

    async def evaluate(self, js):
        return "[]" if "querySelectorAll" in js else self._text

    async def url(self):
        return self._url

    async def title(self):
        return self._title

    async def screenshot(self, **kwargs):
        return self._png


CASES = {
    # No before-picture of the colour, but the click changed the page and the button is now green.
    "incomplete: green button, no before-state": (
        "Click the button and confirm that it changes colour.",
        [
            {"step": 1, "tool": "look", "url": "http://uitestingplayground.com/click",
             "summary": "A page titled Click with a button labelled 'Button That Ignores DOM Click Event'.", "interactive": []},
            {"step": 2, "tool": "do", "instruction": "click the 'Button That Ignores DOM Click Event' button",
             "page_changed": True, "url_after": "http://uitestingplayground.com/click"},
        ],
        FakePage("http://uitestingplayground.com/click", "Click",
                 "Click\nThe button below ignores DOM click events.\nButton That Ignores DOM Click Event", (40, 167, 69)),
    ),
    # The goal needs a login that happened off-record: nothing shows how the page was reached.
    "incomplete: thin record": (
        "Start the loading and read the text that appears when it finishes.",
        [],
        FakePage("https://the-internet.herokuapp.com/dynamic_loading/1", "The Internet",
                 "Dynamically Loaded Page Elements\nExample 1: Element on page that is hidden\nHello World!", (255, 255, 255)),
    ),
    # Positive evidence of failure: error on the page, and the login never changed it.
    "contradicted: error shown": (
        "Log in as locked_out_user and add a product to the cart.",
        [
            {"step": 1, "tool": "look", "url": "https://www.saucedemo.com/", "summary": "A login form.", "interactive": []},
            {"step": 2, "tool": "do", "instruction": "type 'locked_out_user' into the username field",
             "page_changed": True, "url_after": "https://www.saucedemo.com/"},
            {"step": 3, "tool": "do", "instruction": "click the Login button", "page_changed": True,
             "url_after": "https://www.saucedemo.com/"},
        ],
        FakePage("https://www.saucedemo.com/", "Swag Labs",
                 "Epic sadface: Sorry, this user has been locked out.\nUsername\nPassword\nLogin", (255, 255, 255)),
    ),
}


async def main(only=None):
    verify = verifier.verify.__wrapped__
    for name, (goal, record, page) in CASES.items():
        if only and only not in name:
            continue
        results = []
        for _ in range(3):
            r = await verify(goal, record, page)
            results.append(r["verdict"] + ("*" if r.get("downgraded_from") else ""))
            if only:
                print("  reason:", r["reason"]); print("  evidence:", r.get("contradicting_evidence"))
        print(f"{name:<44} {results}")


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
