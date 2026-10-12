"""Tests that a slow page change is not mistaken for "no effect".

Usage: python -m unittest test_slow_change -v

  Unit tests   a stand-in page, no browser, no model: the polling, the recheck between rungs,
               and the final check before an agent issue is recorded.
  Live tests   a real Chrome and the real lookup model against a local page whose button
               navigates client-side after one second. One click, changed, rung a, no agent
               issue. Set SKIP_LIVE_TESTS=1 to skip them.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)
import asyncio
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
os.environ.pop("NEATLOGS_API_KEY", None)  # nothing from a test is exported to a trace

import tools  # noqa: E402


def states(*sequence):
    """A _page_state replacement that returns the given states, then repeats the last one."""
    items = list(sequence)

    async def page_state(with_focus):
        return items.pop(0) if len(items) > 1 else items[0]

    return page_state


BEFORE = "https://app.example/#aaaa"


class Polling(unittest.IsolatedAsyncioTestCase):
    async def test_a_url_change_counts_even_when_nothing_else_changed(self):
        # Same fingerprint hash, different URL: a client-side navigation to a page that looks alike.
        with mock.patch.object(tools, "_page_state", states(("https://app.example/auth", "https://app.example/auth#aaaa"))):
            self.assertTrue(await tools._changed_since(BEFORE, window=0))

    async def test_a_change_one_second_later_is_seen(self):
        started = time.monotonic()
        state = {"changed_at": started + 1.0}

        async def page_state(with_focus):
            if time.monotonic() >= state["changed_at"]:
                return "https://app.example/auth", "https://app.example/auth#bbbb"
            return "https://app.example/", BEFORE

        with mock.patch.object(tools, "_page_state", page_state):
            self.assertTrue(await tools._changed_since(BEFORE))
        self.assertGreaterEqual(time.monotonic() - started, 1.0)

    async def test_no_change_is_reported_after_the_window(self):
        started = time.monotonic()
        with mock.patch.object(tools, "_page_state", states(("https://app.example/", BEFORE))):
            self.assertFalse(await tools._changed_since(BEFORE, window=0.5))
        self.assertGreaterEqual(time.monotonic() - started, 0.5)

    async def test_a_page_that_cannot_be_read_mid_navigation_is_not_a_change_by_itself(self):
        with mock.patch.object(tools, "_page_state", states(None)):
            self.assertFalse(await tools._changed_since(BEFORE, window=0.3))


class Ladder(unittest.IsolatedAsyncioTestCase):
    async def test_a_late_change_stops_the_ladder_before_the_next_rung_clicks(self):
        calls = []

        async def rung_a(instruction):
            calls.append("a")
            return {"reported_success": True, "message": "clicked"}

        async def rung_b(instruction):
            calls.append("b")
            return {"reported_success": True, "message": "clicked", "action": None}

        # Not changed within the window; changed on the recheck made before climbing.
        answers = iter([False, True])

        async def changed(before, with_focus=False, window=tools.SETTLE_WINDOW_S):
            return next(answers)

        with mock.patch.object(tools, "_rung_act_instruction", rung_a), \
                mock.patch.object(tools, "_rung_observe_then_act", rung_b), \
                mock.patch.object(tools, "_changed_since", changed), \
                mock.patch.object(tools, "RECHECK_WAIT_S", 0.01):
            worked, rungs, _ = await tools._ladder("click go", BEFORE, True)
        self.assertEqual(worked, "a")
        self.assertEqual(calls, ["a"], "the page had already moved: nothing was clicked again")
        self.assertTrue(rungs[0]["changed"])
        self.assertTrue(rungs[0]["late"])


class FinalCheck(unittest.IsolatedAsyncioTestCase):
    async def do(self, *, ladder, changed_answers):
        class Page:
            async def url(self):
                return "https://app.example/auth"

            async def evaluate(self, js):
                return ""

        page = Page()
        ctx = tools.RunContext(url="https://app.example/", goal="g", run_id="slow-test", stagehand=None, page=page)
        token = tools.current_run.set(ctx)
        answers = iter(changed_answers)

        async def changed(before, with_focus=False, window=tools.SETTLE_WINDOW_S):
            return next(answers)

        async def active_page():
            return page

        async def now(p):
            return 0.0

        async def collect(p, since):
            return []

        async def screenshot(c, p):
            return None

        async def fingerprint(p, with_focus=False):
            return BEFORE

        try:
            with mock.patch.object(tools, "_ladder", ladder), mock.patch.object(tools, "_changed_since", changed), \
                    mock.patch.object(tools, "_active_page", active_page), \
                    mock.patch.object(tools, "page_fingerprint", fingerprint), \
                    mock.patch.object(tools.page_watch, "now", now), \
                    mock.patch.object(tools.page_watch, "collect", collect), \
                    mock.patch.object(tools, "_screenshot", screenshot):
                result = await tools.do.__wrapped__.__wrapped__("click the Meet your agent button")
        finally:
            tools.current_run.reset(token)
        return result, ctx

    async def test_a_change_after_the_ladder_is_a_success_and_records_nothing(self):
        async def ladder(instruction, before, with_focus):
            return None, [{"rung": "a", "changed": False}, {"rung": "b", "changed": False},
                          {"rung": "c", "skipped": "no observed element to replay"},
                          {"rung": "d", "changed": False, "reported_success": True}], None

        result, ctx = await self.do(ladder=ladder, changed_answers=[True])
        self.assertTrue(result["success"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["rung"], "d", "the rung that was running when the page moved")
        self.assertTrue(result["settled_late"])
        self.assertEqual(ctx.agent_issues, [])
        self.assertEqual(ctx.frictions, [])

    async def test_no_change_at_all_is_still_an_agent_issue(self):
        async def ladder(instruction, before, with_focus):
            return None, [{"rung": "a", "changed": False, "reported_success": True}], None

        result, ctx = await self.do(ladder=ladder, changed_answers=[False])
        self.assertFalse(result["success"])
        self.assertEqual(result["kind"], "agent_issue")
        self.assertEqual(len(ctx.agent_issues), 1)


# ----------------------------------------------------------------- live: a button that navigates late

PAGE = """<!doctype html><html><head><title>Friction Fixer</title></head><body><main id=app>
<h1>Friction Fixer</h1><p>Find where your visitors get stuck.</p>
<button id=go>Meet your agent</button></main>
<script>
window.__clicks = 0;
document.getElementById('go').addEventListener('click', () => {
  window.__clicks += 1;
  setTimeout(() => {              // a client-side navigation that finishes a second after the click
    history.pushState({}, '', '/auth');
    %(change)s
  }, %(delay)d);
});
</script></body></html>"""

REPLACE_CONTENT = "document.getElementById('app').innerHTML = '<h1>Sign in</h1><p>Continue with your email.</p>';"
URL_ONLY = "/* the address changes, the page looks the same */"


class LocalApp(BaseHTTPRequestHandler):
    body = PAGE % {"change": REPLACE_CONTENT, "delay": 1000}

    def log_message(self, *args):
        pass

    def do_GET(self):
        data = self.body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@unittest.skipIf(os.environ.get("SKIP_LIVE_TESTS"), "SKIP_LIVE_TESTS is set")
class SlowClientSideNavigation(unittest.IsolatedAsyncioTestCase):
    async def click_once(self, body: str):
        import egress
        from browser import close_browser, open_browser

        handler = type("Handler", (LocalApp,), {"body": body})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = egress.is_blocked_address
        egress.is_blocked_address = lambda address: False if str(address) == "127.0.0.1" else original(address)
        browser, stagehand, page, guard = await open_browser()
        ctx = tools.RunContext(url="http://127.0.0.1/", goal="g", run_id="slow-live", stagehand=stagehand, page=page)
        token = tools.current_run.set(ctx)
        try:
            await page.goto(f"http://127.0.0.1:{server.server_address[1]}/", wait_until="domcontentloaded")
            await page.wait_for_selector("#go")
            result = await tools.do("click the 'Meet your agent' button")
            clicks = await page.evaluate("window.__clicks")
            final_url = await page.url()
        finally:
            tools.current_run.reset(token)
            egress.is_blocked_address = original
            server.shutdown()
            await close_browser(browser, stagehand, guard)
        return result, ctx, clicks, final_url

    async def test_a_click_that_navigates_after_a_second(self):
        result, ctx, clicks, final_url = await self.click_once(PAGE % {"change": REPLACE_CONTENT, "delay": 1000})
        self.assertEqual(clicks, 1, "one click: the ladder did not climb")
        self.assertTrue(result["changed"])
        self.assertTrue(result["success"])
        self.assertEqual(result["rung"], "a")
        self.assertEqual(ctx.agent_issues, [])
        self.assertTrue(final_url.endswith("/auth"))

    async def test_a_url_only_change_counts(self):
        result, ctx, clicks, final_url = await self.click_once(PAGE % {"change": URL_ONLY, "delay": 1000})
        self.assertEqual(clicks, 1)
        self.assertTrue(result["changed"])
        self.assertEqual(result["rung"], "a")
        self.assertEqual(ctx.agent_issues, [])
        self.assertTrue(final_url.endswith("/auth"))

    async def test_a_click_that_navigates_after_two_and_a_half_seconds(self):
        # Later than the old fixed wait (1.6 s) and than the polling window (2 s): found by the recheck
        # made before climbing to the next rung, so nothing is clicked a second time.
        result, ctx, clicks, final_url = await self.click_once(PAGE % {"change": REPLACE_CONTENT, "delay": 2500})
        self.assertEqual(clicks, 1, "one click: the page had not moved yet, but it was not clicked again")
        self.assertTrue(result["changed"])
        self.assertEqual(result["rung"], "a")
        self.assertEqual(ctx.agent_issues, [])
        self.assertTrue(final_url.endswith("/auth"))


if __name__ == "__main__":
    unittest.main()
