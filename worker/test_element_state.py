"""The target element's state before and after an action, and bot checks.

  Unit tests   colour names, matching an instruction to an element, what changed, how the verifier sees it
  Live tests   a real Chrome behind the egress guard and the real model (a few cents):
               a button that turns green on click, and a page that shows a bot check.
               SKIP_LIVE_TESTS=1 skips them.
Nothing here names a site: the page is a local one written for the test.
"""

import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import bot_check
import element_state as es
import verifier


def state(i, label, cls="btn btn-primary", color="rgb(255, 255, 255)", background="rgb(0, 123, 255)",
          aria=None, disabled=False, checked=None, tag="button"):
    return {"i": i, "connected": True, "tag": tag, "role": "", "label": label, "cls": cls, "aria": aria or {},
            "disabled": disabled, "checked": checked, "color": color, "background": background}


class ColourNames(unittest.TestCase):
    def test_common_colours(self):
        names = {
            "rgb(40, 167, 69)": "green", "rgb(0, 123, 255)": "blue", "rgb(220, 53, 69)": "red",
            "rgb(255, 193, 7)": "yellow", "rgb(255, 255, 255)": "white", "rgb(0, 0, 0)": "black",
            "rgb(128, 128, 128)": "grey", "rgb(255, 128, 0)": "orange", "rgb(111, 66, 193)": "purple",
        }
        for value, word in names.items():
            self.assertIn(f"({word})", es.colour_name(value), value)

    def test_transparent_and_alpha(self):
        self.assertEqual(es.colour_name("rgba(0, 0, 0, 0)"), "transparent")
        self.assertIn("at 0.5 opacity", es.colour_name("rgba(40, 167, 69, 0.5)"))
        self.assertEqual(es.colour_name(None), "none")
        self.assertEqual(es.colour_name("red"), "red")


class PickingTheTarget(unittest.TestCase):
    STATES = [state(0, "Home", tag="a"), state(1, "Button That Ignores DOM Click Event"),
              state(2, "Add to cart"), state(3, "Add to cart for the blue mug"), state(4, "")]

    def test_a_quoted_label_wins_exact_then_contained(self):
        found, how = es.best_match("click the 'Button That Ignores DOM Click Event' button", self.STATES)
        self.assertEqual(found["i"], 1)
        self.assertIn("quoted label", how)
        found, _ = es.best_match("click \"Add to cart\"", self.STATES)
        self.assertEqual(found["i"], 2, "an exact label beats one that merely contains it")

    def test_without_quotes_most_of_the_labels_words_must_be_in_the_instruction(self):
        found, how = es.best_match("click the Add to cart for the blue mug button", self.STATES)
        self.assertEqual(found["i"], 3)
        self.assertIsNone(es.best_match("do the next thing", self.STATES))
        self.assertIsNone(es.best_match("click the big thing", [state(0, "Subscribe to our newsletter")]))

    def test_an_instruction_that_matches_nothing_claims_nothing(self):
        self.assertIsNone(es.best_match("click 'Nonexistent'", self.STATES))
        self.assertIsNone(es.best_match("click it", []))


class WhatChanged(unittest.TestCase):
    def snapshots(self):
        before = [state(0, "Home", tag="a"),
                  state(1, "Button That Ignores DOM Click Event"),
                  state(2, "Subscribe", cls="btn")]
        after = [dict(before[0]),
                 {**before[1], "cls": "btn btn-success", "background": "rgb(40, 167, 69)"},
                 dict(before[2])]
        return before, after

    def test_a_button_turning_green_is_recorded_with_both_states(self):
        before, after = self.snapshots()
        entry = es.describe_change("click the 'Button That Ignores DOM Click Event' button", before, after)
        target = entry["target"]
        self.assertEqual(target["before"]["background"], "rgb(0, 123, 255) (blue)")
        self.assertEqual(target["after"]["background"], "rgb(40, 167, 69) (green)")
        self.assertEqual(target["before"]["class"], "btn btn-primary")
        self.assertEqual(target["after"]["class"], "btn btn-success")
        self.assertEqual(target["changed"], [
            "class: 'btn btn-primary' -> 'btn btn-success'",
            "background colour: rgb(0, 123, 255) (blue) -> rgb(40, 167, 69) (green)",
        ])
        self.assertNotIn("others_changed", entry)

    def test_aria_text_and_checked_changes_are_recorded(self):
        before = [state(0, "Mute", aria={"aria-pressed": "false"}), state(1, "Done", tag="input", checked=False)]
        after = [state(0, "Unmute", aria={"aria-pressed": "true"}), state(1, "Done", tag="input", checked=True)]
        entry = es.describe_change("click 'Mute'", before, after)
        joined = " ".join(entry["target"]["changed"])
        self.assertIn("text: 'Mute' -> 'Unmute'", joined)
        self.assertIn("ARIA state", joined)
        self.assertEqual(entry["others_changed"][0]["changed"], ["checked: False -> True"])

    def test_other_elements_that_changed_are_listed_when_the_target_is_not_known(self):
        before, after = self.snapshots()
        entry = es.describe_change("click the big thing", before, after)
        self.assertNotIn("target", entry)
        self.assertEqual(entry["others_changed"][0]["label"], "Button That Ignores DOM Click Event")

    def test_no_change_and_no_snapshot_say_nothing_false(self):
        before, _ = self.snapshots()
        same = es.describe_change("click 'Subscribe'", before, [dict(s) for s in before])
        self.assertEqual(same["target"]["changed"], [])
        self.assertIsNone(es.describe_change("click 'x'", None, before))
        self.assertIsNone(es.describe_change("click 'x'", before, None), "a navigation reset the page")
        self.assertIsNone(es.describe_change("click 'x'", before, before[:1]))
        self.assertIsNone(es.describe_change("click the big thing", before, [dict(s) for s in before]))

    def test_the_sentence_for_the_record_has_both_states_and_the_change(self):
        before, after = self.snapshots()
        text = es.format_for_record(
            es.describe_change("click the 'Button That Ignores DOM Click Event' button", before, after))
        self.assertIn("before: ", text)
        self.assertIn("background rgb(0, 123, 255) (blue)", text)
        self.assertIn("after: ", text)
        self.assertIn("background rgb(40, 167, 69) (green)", text)
        self.assertIn("changed: class:", text)
        self.assertEqual(es.format_for_record(None), "")


class TheVerifierSeesIt(unittest.TestCase):
    def test_the_record_the_verifier_reads_includes_the_element(self):
        before = [state(0, "Button That Ignores DOM Click Event")]
        after = [{**before[0], "background": "rgb(40, 167, 69)", "cls": "btn btn-success"}]
        element = es.describe_change("click the 'Button That Ignores DOM Click Event' button", before, after)
        record = [{"step": 2, "tool": "do", "instruction": "click the 'Button That Ignores DOM Click Event' button",
                   "page_changed": True, "url_after": "http://x.test/click", "element": element}]
        text = verifier.format_record(record)
        self.assertIn("(blue)", text)
        self.assertIn("(green)", text)
        self.assertIn("page changed", text)
        without = verifier.format_record([{k: v for k, v in record[0].items() if k != "element"}])
        self.assertNotIn("(green)", without)

    def test_the_verifiers_rules_for_contradicting_are_unchanged(self):
        prompt = verifier.SYSTEM_PROMPT
        self.assertIn("Something that is merely ABSENT is never contradicting evidence", prompt)
        self.assertIn("when in doubt between contradicted and unverified, choose unverified", prompt)
        self.assertIn("no difference, or no entry, says nothing either way", prompt)


class BotCheckWords(unittest.TestCase):
    def test_challenge_pages_are_recognised(self):
        for title, text, frames, widget in [
            ("Just a moment...", "Verify you are human by completing the action below.", 0, False),
            ("practicesoftwaretesting.com", "Checking if the site connection is secure", 0, False),
            ("Login", "Please tick: I'm not a robot", 0, False),
            ("Attention Required! | Cloudflare", "Sorry, you have been blocked", 1, False),
            ("Verify", "Press and hold the button", 0, False),
        ]:
            self.assertIsNotNone(bot_check.classify(title, text, frames, widget), (title, text))

    def test_ordinary_pages_are_not(self):
        for title, text, frames, widget in [
            ("Log in", "Email Password Log in. This site is protected by reCAPTCHA.", 0, False),
            ("Humans of New York", "Stories of real people", 0, False),
            ("Access denied", "You do not have permission to view this page", 0, False),  # no challenge frame
            ("Shop", "Add to cart. Verify your email address to continue", 0, False),
        ]:
            self.assertIsNone(bot_check.classify(title, text, frames, widget), (title, text))

    def test_the_reason_says_nothing_was_attempted(self):
        reason = bot_check.reason({"phrase": "Verify you are human", "url": "https://shop.test/"})
        self.assertIn("does not try to get past", reason)
        self.assertIn("blocked by a bot check", reason)


# ----------------------------------------------------------------- live

GREEN_PAGE = """<!doctype html><html><head><title>Click</title><style>
.btn { padding: 12px 20px; border: 0; color: white; font-size: 16px; }
.btn-primary { background: rgb(0, 123, 255); } .btn-success { background: rgb(40, 167, 69); }
</style></head><body><h1>Click test</h1>
<p>The button changes colour after a click.</p>
<button id=b class="btn btn-primary">Button That Ignores DOM Click Event</button>
<script>document.getElementById('b').addEventListener('click', (e) => {
  e.target.className = 'btn btn-success'; });</script></body></html>"""

CHALLENGE_PAGE = """<!doctype html><html><head><title>Just a moment...</title></head><body>
<h1>practice.example</h1><p>Verify you are human by completing the action below.</p>
<label><input type=checkbox id=human> Verify you are human</label>
<script>window.__touched = 0; document.getElementById('human').addEventListener('click', () => { window.__touched += 1; });
</script></body></html>"""


class Page(BaseHTTPRequestHandler):
    body = GREEN_PAGE

    def log_message(self, *args):
        pass

    def do_GET(self):
        data = type(self).body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@unittest.skipIf(os.environ.get("SKIP_LIVE_TESTS"), "SKIP_LIVE_TESTS is set")
class LiveBrowser(unittest.IsolatedAsyncioTestCase):
    async def visit_page(self, body, work):
        import egress
        import tools
        from browser import close_browser, open_browser

        handler = type("Handler", (Page,), {"body": body})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = egress.is_blocked_address
        egress.is_blocked_address = lambda address: False if str(address) == "127.0.0.1" else original(address)
        browser, stagehand, page, guard = await open_browser()
        ctx = tools.RunContext(url="http://127.0.0.1/", goal="g", run_id="element-live", stagehand=stagehand,
                               page=page)
        token = tools.current_run.set(ctx)
        try:
            await page.goto(f"http://127.0.0.1:{server.server_address[1]}/", wait_until="domcontentloaded")
            return await work(tools, ctx, page)
        finally:
            tools.current_run.reset(token)
            egress.is_blocked_address = original
            server.shutdown()
            await close_browser(browser, stagehand, guard)

    async def test_a_button_turning_green_is_in_the_step_record(self):
        async def work(tools, ctx, page):
            result = await tools.do("click the 'Button That Ignores DOM Click Event' button")
            return result, ctx

        import browse

        result, ctx = await self.visit_page(GREEN_PAGE, work)
        self.assertTrue(result["success"])
        target = result["element"]["target"]
        self.assertEqual(target["before"]["background"], "rgb(0, 123, 255) (blue)")
        self.assertEqual(target["after"]["background"], "rgb(40, 167, 69) (green)")
        self.assertIn("class: 'btn btn-primary' -> 'btn btn-success'", target["changed"])
        # The step record the verifier reads carries it.
        browse.record_step(ctx, 1, "do", {"instruction": "x"}, result, None)
        self.assertIn("(green)", verifier.format_record(ctx.record))

    async def test_a_bot_check_ends_the_visit_untouched(self):
        async def work(tools, ctx, page):
            looked = await tools.look()
            clicked = await page.evaluate("window.__touched")
            return looked, ctx, clicked

        looked, ctx, clicked = await self.visit_page(CHALLENGE_PAGE, work)
        self.assertTrue(looked["bot_check"])
        self.assertEqual(ctx.finished["outcome"], "blocked")
        self.assertEqual(ctx.finished["stopped_by"], "bot_check")
        self.assertIn("bot check", ctx.finished["reason"])
        self.assertEqual(ctx.entry["bot_check"]["phrase"].lower(), "verify you are human")
        self.assertEqual(clicked, 0, "the check was not clicked")

    async def test_an_action_on_a_bot_check_is_refused_and_not_attempted(self):
        async def work(tools, ctx, page):
            result = await tools.do("click the 'Verify you are human' checkbox")
            return result, ctx, await page.evaluate("window.__touched")

        result, ctx, clicked = await self.visit_page(CHALLENGE_PAGE, work)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "bot_check")
        self.assertEqual(ctx.finished["stopped_by"], "bot_check")
        self.assertEqual(clicked, 0)
        self.assertEqual(ctx.agent_issues, [], "not blamed on our tool")


class WorkerIdOnClaim(unittest.IsolatedAsyncioTestCase):
    async def test_the_worker_passes_its_host_and_version(self):
        import asyncio

        import worker_loop

        seen = []

        class Db:
            async def claim_run(self, worker_id=None):
                seen.append(worker_id)
                return None

            async def fail_stale_runs(self, minutes):
                return []

            async def delete_old_run_secrets(self, minutes):
                return None

        worker = worker_loop.Worker("abc1234", db=Db(), execute=None, brain_model="m", health_interval=60,
                                    idle_seconds=0.05)
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.2)
        worker.request_stop("test")
        await task
        self.assertTrue(seen)
        self.assertTrue(all(w == worker.worker_id for w in seen))
        self.assertRegex(worker.worker_id, r".+@abc1234$")

    async def test_a_database_without_the_new_function_still_claims(self):
        import db

        calls = []

        class Rpc:
            def __init__(self, name, params):
                self.name, self.params = name, params

            async def execute(self):
                calls.append((self.name, self.params))
                if self.params:
                    raise Exception("PGRST202 Could not find the function public.claim_run(p_worker_id)")
                return type("R", (), {"data": []})()

        class Client:
            def rpc(self, name, params=None):
                return Rpc(name, params)

        async def fake_client():
            return Client()

        original, flag = db.client, db._claim_takes_worker_id
        db.client, db._claim_takes_worker_id = fake_client, True
        try:
            self.assertIsNone(await db.claim_run("host@v"))
            self.assertIsNone(await db.claim_run("host@v"))
        finally:
            db.client, db._claim_takes_worker_id = original, flag
        self.assertEqual(calls, [("claim_run", {"p_worker_id": "host@v"}), ("claim_run", None),
                                 ("claim_run", None)], "tries once with the id, then stops trying")


class EvalScoring(unittest.TestCase):
    def test_bot_checked_runs_are_counted_and_named(self):
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "evals"
        sys.path.insert(0, str(root))
        os.environ.setdefault("NEATLOGS_API_KEY", "test-not-a-real-key-0000000000")
        import importlib.util

        spec = importlib.util.spec_from_file_location("eval_run_module", root / "run.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        case = {"id": "shop", "kind": "achievable", "url": "u", "goal": "g"}
        row = {"id": "r1", "status": "done", "outcome": "blocked", "reason": "bot check", "cost_usd": 0.01,
               "worker_id": "host@abc", "result": {"stopped_by": "bot_check", "steps": 1,
                                                   "entry": {"bot_check": {"phrase": "Verify you are human"}}}}
        per_case, metrics = module.score([case], {"r1": row}, {"shop": "r1"}, {}, {})
        self.assertTrue(per_case[0]["blocked_by_bot_check"])
        self.assertEqual(per_case[0]["completion"], "bot_check")
        self.assertEqual(per_case[0]["worker_id"], "host@abc")
        self.assertEqual(metrics["blocked_by_bot_check"], 1)
        self.assertEqual(module.case_score(per_case[0]), "not completed (blocked by a bot check)")
        markdown = module.markdown("v", per_case, metrics, {
            "finished_at": "now", "agent_versions": ["a"], "brain_models": ["m"], "workers": ["host@abc"],
            "worker_id_column": True})
        self.assertIn("Worker: host@abc (every run).", markdown)
        self.assertIn("blocked by a bot check", markdown)


if __name__ == "__main__":
    unittest.main()
