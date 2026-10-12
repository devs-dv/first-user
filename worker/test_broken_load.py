"""A page whose own scripts fail to load: reloaded like a person would, and reported if it stays broken.

The cause behind the eval's two the-internet.herokuapp.com failures: the site answers some of its
static files with a 503 after 30 seconds, intermittently, with or without our proxy. The page then
loads without its scripts ("$ is not defined", buttons that do nothing).

  Unit tests   what counts as a failed asset (same-site scripts and stylesheets only)
  Live tests   a local server that fails a script a set number of times, in a real Chrome behind the
               egress guard; one test also clicks a button with the real model (a few cents).
               SKIP_LIVE_TESTS=1 skips them.
"""

import asyncio
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import page_watch
import tools
import visit


class FakePage:
    def __init__(self, entries, url="https://app.test/page"):
        self.entries, self._url = entries, url

    async def evaluate(self, expression):
        return json.dumps(self.entries)

    async def url(self):
        return self._url


def entry(text, tag, kind="request"):
    return {"kind": kind, "text": text, "t": 1, "tag": tag}


class FailedAssets(unittest.IsolatedAsyncioTestCase):
    async def test_only_the_pages_own_scripts_and_stylesheets_count(self):
        page = FakePage([
            entry("failed to load https://app.test/js/jquery.js", "script"),
            entry("failed to load https://cdn.app.test/app.css", "style"),
            entry("failed to load https://app.test/img/logo.png", "img"),         # an image is not the page
            entry("failed to load https://tracker.example.net/t.js", "script"),   # another site
            entry("failed to load https://app.test/js/jquery.js", "script"),      # the same file twice
            entry("500 https://app.test/api/x", "", kind="request"),             # a failed request, not a file
            entry("boom", "", kind="js_error"),
        ])
        found = await page_watch.failed_assets(page)
        self.assertEqual(found, [
            {"url": "https://app.test/js/jquery.js", "tag": "script"},
            {"url": "https://cdn.app.test/app.css", "tag": "style"},
        ])

    async def test_an_unreadable_log_is_no_failure(self):
        class Broken:
            async def evaluate(self, expression):
                raise RuntimeError("navigating")

        self.assertEqual(await page_watch.failed_assets(Broken()), [])

    def test_the_description_uses_file_names(self):
        assets = [{"url": f"https://app.test/js/f{i}.js", "tag": "script"} for i in range(5)]
        self.assertEqual(page_watch.describe_assets(assets), "f0.js, f1.js, f2.js and 2 more")


# ----------------------------------------------------------------- live

PAGE = """<!doctype html><html><head><title>Elements</title></head><body>
<h1>Add/Remove</h1><button id=add>Add Element</button><div id=out></div>
<script src="/js/app.js"></script>
<script>document.getElementById('add').addEventListener('click', () => { $('#out').append('<button>Delete</button>'); });</script>
</body></html>"""
SCRIPT = "window.$ = (selector) => ({ append: (html) => { document.querySelector(selector).innerHTML += html; } });"


class FlakyScriptSite(BaseHTTPRequestHandler):
    """/js/app.js answers 503 `fail_first` times (then 200), or always when fail_first is None."""
    fail_first: int | None = 1
    requests: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        cls = type(self)
        if self.path == "/js/app.js":
            cls.requests.append(self.path)
            failing = cls.fail_first is None or len(cls.requests) <= cls.fail_first
            body, status = (b"upstream timeout", 503) if failing else (SCRIPT.encode(), 200)
            ctype = "text/plain" if failing else "application/javascript"
        else:
            body, status, ctype = PAGE.encode(), 200, "text/html; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


@unittest.skipIf(os.environ.get("SKIP_LIVE_TESTS"), "SKIP_LIVE_TESTS is set")
class ReloadLikeAPerson(unittest.IsolatedAsyncioTestCase):
    async def open_page(self, fail_first, act=None):
        import egress
        from browser import close_browser, open_browser

        handler = type("Handler", (FlakyScriptSite,), {"fail_first": fail_first, "requests": []})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = egress.is_blocked_address
        egress.is_blocked_address = lambda address: False if str(address) == "127.0.0.1" else original(address)
        browser, stagehand, page, guard = await open_browser()
        try:
            await page_watch.install(page)
            await visit.open_start_page(page, f"http://127.0.0.1:{server.server_address[1]}/", guard)
            ready = await page.evaluate("typeof window.$")
            extra = await act(page, stagehand) if act else None
            return ready, len(handler.requests), guard.blocks, extra
        finally:
            egress.is_blocked_address = original
            server.shutdown()
            await close_browser(browser, stagehand, guard)

    async def test_a_script_that_fails_once_is_loaded_by_the_reload(self):
        ready, requests, blocks, _ = await self.open_page(fail_first=1)
        self.assertEqual(ready, "function", "the page's script is there after the reload")
        self.assertEqual(requests, 2, "one failed load, one reload")
        self.assertEqual(blocks, [])

    async def test_a_page_that_loads_whole_is_not_reloaded(self):
        ready, requests, _, _ = await self.open_page(fail_first=0)
        self.assertEqual(ready, "function")
        self.assertEqual(requests, 1)

    async def test_a_script_that_never_loads_is_reloaded_twice_and_then_left_alone(self):
        ready, requests, _, _ = await self.open_page(fail_first=None)
        self.assertEqual(ready, "undefined")
        self.assertEqual(requests, 1 + visit.MAX_RELOADS)

    async def test_a_click_that_needs_the_missing_script_is_the_sites_friction_not_ours(self):
        async def click(page, stagehand):
            ctx = tools.RunContext(url="http://127.0.0.1/", goal="g", run_id="broken-load", stagehand=stagehand,
                                   page=page)
            token = tools.current_run.set(ctx)
            try:
                await page.wait_for_selector("#add")
                result = await tools.do("click the 'Add Element' button")
            finally:
                tools.current_run.reset(token)
            return result, ctx

        _, requests, _, (result, ctx) = await self.open_page(fail_first=None, act=click)
        self.assertFalse(result["success"])
        self.assertEqual(ctx.agent_issues, [], "our tool is not blamed")
        self.assertEqual(len(ctx.frictions), 1)
        friction = ctx.frictions[0]
        self.assertEqual(friction["kind"], "site")
        # Either the page threw because its script was missing, or nothing happened and the failed
        # file is named: both are the site's, and neither is ours.
        self.assertIn(friction["detected_by"], ("page_errors", "failed_assets"))
        self.assertTrue("is not defined" in friction["happened"] or "app.js" in friction["happened"],
                        friction["happened"])
        self.assertEqual(result["kind"], "site_problem")


if __name__ == "__main__":
    unittest.main()
