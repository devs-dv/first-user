"""Tests that a founder's test login never ends up anywhere it should not.

Usage: python -m unittest test_credentials -v

  Unit tests         no browser, no model: the holder, scrubbing, the neatlogs mask, the run lifecycle.
  Browser test       a real Chrome, no model: screenshots are taken with the login hidden in the page.
  End-to-end tests   the real worker path with a real model against a local site with a login,
                     a sign-up, an email-verification page and a "Google only" page (a few cents).
                     Set SKIP_LIVE_TESTS=1 to skip them.

After a run with test credentials, the end-to-end tests search for the login in: what the database
would be given (results, steps, frictions, the first impression), every exported span (after the
mask), every request to a model, the process's own output, and what the page showed while a
screenshot was taken. All must be free of it, and the stand-in database must hold no login.
"""

import asyncio
import copy
import json
import os
import pickle
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from neatlogs.core.masking_exporter import MaskingSpanExporter
from neatlogs.decorators._base import _safe_json_dumps
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import credentials
import trace_safety
import worker_run

HERE = Path(__file__).parent
EMAIL = "qa.tester@example.org"
PASSWORD = "Hunter2-Zebra-77!"


def with_secrets_registered(test):
    """Run a test with a clean registry, and leave it clean."""
    def wrapper(self, *args, **kwargs):
        trace_safety.forget_secrets()
        try:
            return test(self, *args, **kwargs)
        finally:
            trace_safety.forget_secrets()
    return wrapper


class TheHolderIsOpaque(unittest.TestCase):
    def test_repr_and_str_show_nothing(self):
        creds = credentials.TestCredentials(EMAIL, PASSWORD)
        for text in (repr(creds), str(creds), f"{creds}", f"{creds!r}", json.dumps({"c": str(creds)})):
            self.assertNotIn(EMAIL, text)
            self.assertNotIn(PASSWORD, text)

    def test_a_serializer_that_walks_attributes_finds_nothing(self):
        creds = credentials.TestCredentials(EMAIL, PASSWORD)
        self.assertFalse(hasattr(creds, "__dict__"))
        # What @neatlogs.span records for a traced function's argument, which is how a key leaked before.
        recorded = _safe_json_dumps({"credentials": creds, "ctx": {"credentials": creds}})
        self.assertNotIn(EMAIL, recorded)
        self.assertNotIn(PASSWORD, recorded)

    def test_it_cannot_be_copied_or_pickled(self):
        creds = credentials.TestCredentials(EMAIL, PASSWORD)
        with self.assertRaises(TypeError):
            pickle.dumps(creds)
        with self.assertRaises(TypeError):
            copy.deepcopy(creds)

    def test_a_generated_identity(self):
        first, second = credentials.generate_identity(), credentials.generate_identity()
        self.assertNotEqual(first.email, second.email)
        self.assertTrue(re.fullmatch(r"first\.user\.[0-9a-f]{8}@example\.com", first.email))
        password = first.credentials.password
        self.assertGreaterEqual(len(password), 14)
        self.assertTrue(any(c.isupper() for c in password) and any(c.islower() for c in password))
        self.assertTrue(any(c.isdigit() for c in password) and any(not c.isalnum() for c in password))
        self.assertNotIn(password, repr(first))


class ScrubbingAndTheMask(unittest.TestCase):
    @with_secrets_registered
    def test_scrub_replaces_values_with_labels_everywhere(self):
        credentials.TestCredentials(EMAIL, PASSWORD).register()
        data = {
            "message": f"Signed in as {EMAIL.upper()} with {PASSWORD}",
            "list": [f"[{PASSWORD}]", {"nested": f"user={EMAIL}"}],
            "count": 3,
        }
        cleaned = json.dumps(trace_safety.scrub(data))
        self.assertNotIn(EMAIL.lower(), cleaned.lower())
        self.assertNotIn(PASSWORD, cleaned)
        self.assertIn("[test email]", cleaned)
        self.assertIn("[test password]", cleaned)
        self.assertEqual(trace_safety.scrub(data)["count"], 3)

    @with_secrets_registered
    def test_exported_spans_are_redacted(self):
        credentials.TestCredentials(EMAIL, PASSWORD).register()
        sink = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(MaskingSpanExporter(sink, trace_safety.mask)))
        span = provider.get_tracer("test").start_span(
            f"typed {PASSWORD}",
            attributes={
                "input.value": json.dumps({"instruction": f"type {PASSWORD} into the field", "who": EMAIL}),
                "output.value": f"Welcome back, {EMAIL}",
                "neatlogs.llm.input_messages.2.content": f"The password field now holds {PASSWORD}",
            },
        )
        span.add_event("exception", {"exception.message": f"Timeout typing {PASSWORD} for {EMAIL}"})
        span.end()
        provider.shutdown()
        exported = json.dumps([(s.name, dict(s.attributes), [(e.name, dict(e.attributes)) for e in s.events])
                               for s in sink.get_finished_spans()])
        self.assertNotIn(PASSWORD, exported)
        self.assertNotIn(EMAIL, exported)

    def test_third_party_logins_are_refused(self):
        for text in ("click Continue with Google", "Sign in with GitHub", "log in using Microsoft SSO",
                     "press the 'Sign up with Apple' button"):
            self.assertTrue(credentials.is_third_party_login(text), text)
        for text in ("click the Login button", "type 'a' into the Google search box", "click Sign up"):
            self.assertFalse(credentials.is_third_party_login(text), text)


class RecordingPage:
    """A stand-in page that records every script it is sent, and shows some text."""

    def __init__(self, texts, values=()):
        self.texts, self.values = list(texts), list(values)
        self.scripts: list[str] = []
        self.applied: list[tuple] = []
        self.restored = 0

    async def evaluate(self, script):
        self.scripts.append(script)
        if "__firstUserNodes = []" in script:  # collect
            return json.dumps({"texts": self.texts, "values": self.values})
        if "undo.push" in script and "textChanges" in script:  # apply
            self.applied.append(script)
            return 1
        if "__firstUserRestore" in script:
            self.restored += 1
            return 0
        raise AssertionError("unexpected script")


class SecretsAreNeverSentIntoAPage(unittest.IsolatedAsyncioTestCase):
    """A page under test is not trusted: script in it can hook built-ins and watch what we run there."""

    def setUp(self):
        trace_safety.forget_secrets()

    def tearDown(self):
        trace_safety.forget_secrets()

    async def test_redaction_sends_only_indexes_and_labels(self):
        other_run = "Other-Tenant-Pw-9911!"
        credentials.TestCredentials(EMAIL, PASSWORD).register()
        trace_safety.register_secret(other_run, "[redacted]")
        page = RecordingPage(
            [f"Signed in as {EMAIL}", "Projects", f"debug: {PASSWORD}"], values=["nothing", EMAIL]
        )
        async with credentials.redacted_page(page):
            pass
        sent = "\n".join(page.scripts)
        for secret in (EMAIL, EMAIL.upper(), PASSWORD, other_run):
            self.assertNotIn(secret, sent)
        self.assertEqual(len(page.applied), 1)
        self.assertIn("[test email]", page.applied[0])
        self.assertIn("[test password]", page.applied[0])
        self.assertEqual(page.restored, 1, "the page is put back")

    async def test_a_page_that_shows_nothing_is_not_touched(self):
        credentials.TestCredentials(EMAIL, PASSWORD).register()
        page = RecordingPage(["Welcome", "Projects and tasks"])
        async with credentials.redacted_page(page):
            pass
        self.assertEqual(page.applied, [])

    async def test_a_failed_swap_means_no_capture(self):
        credentials.TestCredentials(EMAIL, PASSWORD).register()

        class Broken(RecordingPage):
            async def evaluate(self, script):
                if "__firstUserNodes = []" in script:
                    raise RuntimeError("page closed")
                return await super().evaluate(script)

        with self.assertRaises(RuntimeError):
            async with credentials.redacted_page(Broken([f"hello {EMAIL}"])):
                self.fail("the body must not run when the secrets could not be hidden")


class FakeDb:
    """The parts of db.py that worker_run uses, with the database's behaviour for run_secrets."""

    def __init__(self, secrets=None, fail_reading=False):
        self.secrets = dict(secrets or {})
        self.fail_reading = fail_reading
        self.take_calls = self.delete_calls = 0
        self.saved: list[dict] = []

    async def take_run_secrets(self, run_id):
        self.take_calls += 1
        if self.fail_reading:
            raise RuntimeError("function public.take_run_secrets does not exist")
        row = self.secrets.pop(run_id, None)
        return {"email": row[0], "password": row[1]} if row else None

    async def delete_run_secrets(self, run_id):
        self.delete_calls += 1
        self.secrets.pop(run_id, None)

    async def finish_run(self, run_id, result, agent_version, brain_model):
        self.saved.append({"kind": "finish", "result": result})

    async def fail_run(self, run_id, error, agent_version=None, brain_model=None, result=None):
        self.saved.append({"kind": "fail", "error": error, "result": result})

    class RunRecorder:
        def __init__(self, run_id):
            pass


class RunLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        trace_safety.forget_secrets()

    def tearDown(self):
        trace_safety.forget_secrets()

    async def execute(self, fake, first_visit, run):
        with mock.patch.multiple(worker_run.db, take_run_secrets=fake.take_run_secrets,
                                 delete_run_secrets=fake.delete_run_secrets, finish_run=fake.finish_run,
                                 fail_run=fake.fail_run, RunRecorder=fake.RunRecorder), \
                mock.patch.object(worker_run, "first_visit", first_visit):
            await worker_run.execute(run, "test")

    async def test_the_login_is_taken_used_and_cleared_on_success(self):
        fake = FakeDb({"r1": (EMAIL, PASSWORD)})
        seen = {}

        async def first_visit(url, goal, run_id, recorder=None, start_url=None, credentials=None,
                              test_login_unavailable=False, access_mode="signup"):
            seen.update(email=credentials.email, password=credentials.password, start_url=start_url,
                        database_holds_login=bool(fake.secrets))
            return {"outcome": "achieved", "steps": 1, "reason": "ok"}

        await self.execute(fake, first_visit, {"id": "r1", "url": "https://x.example", "goal": "g",
                                               "start_url": "https://x.example/demo", "has_test_login": True})
        self.assertEqual((seen["email"], seen["password"]), (EMAIL, PASSWORD))
        self.assertFalse(seen["database_holds_login"], "the login is deleted when it is read, before the visit")
        self.assertEqual(seen["start_url"], "https://x.example/demo")
        self.assertEqual(fake.secrets, {})
        self.assertEqual(fake.delete_calls, 1)
        self.assertEqual([s["kind"] for s in fake.saved], ["finish"])

    async def test_the_login_is_cleared_when_the_visit_fails_and_the_error_is_scrubbed(self):
        fake = FakeDb({"r2": (EMAIL, PASSWORD)})

        async def first_visit(*args, **kwargs):
            raise RuntimeError(f"Could not type {PASSWORD} for {EMAIL}")

        buffer = tempfile.TemporaryFile("w+")
        with mock.patch("sys.stdout", buffer):
            await self.execute(fake, first_visit, {"id": "r2", "url": "https://x.example", "goal": "g",
                                                   "has_test_login": True})
        buffer.seek(0)
        printed = buffer.read()
        self.assertEqual(fake.secrets, {})
        self.assertGreaterEqual(fake.delete_calls, 1)
        self.assertEqual([s["kind"] for s in fake.saved], ["fail"])
        everything = json.dumps(fake.saved) + printed
        self.assertNotIn(PASSWORD, everything)
        self.assertNotIn(EMAIL, everything)

    async def test_a_run_without_a_login_never_asks_for_one(self):
        fake = FakeDb()

        async def first_visit(url, goal, run_id, recorder=None, start_url=None, credentials=None,
                              test_login_unavailable=False, access_mode="signup"):
            self.assertIsNone(credentials)
            self.assertFalse(test_login_unavailable)
            return {"outcome": "gave_up", "steps": 2, "reason": "r"}

        await self.execute(fake, first_visit, {"id": "r3", "url": "https://x.example", "goal": "g",
                                               "has_test_login": False})
        self.assertEqual(fake.take_calls, 0)

    async def test_a_login_that_cannot_be_read_is_reported_not_guessed(self):
        fake = FakeDb({"r4": (EMAIL, PASSWORD)}, fail_reading=True)
        seen = {}

        async def first_visit(url, goal, run_id, recorder=None, start_url=None, credentials=None,
                              test_login_unavailable=False, access_mode="signup"):
            seen.update(credentials=credentials, unavailable=test_login_unavailable)
            return {"outcome": "blocked", "steps": 1, "reason": "login"}

        await self.execute(fake, first_visit, {"id": "r4", "url": "https://x.example", "goal": "g",
                                               "has_test_login": True})
        self.assertIsNone(seen["credentials"])
        self.assertTrue(seen["unavailable"])
        self.assertEqual(fake.secrets, {}, "the safety-net delete still ran")


# ----------------------------------------------------------------- a real browser, no model

class _Page(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = (f"<html><body><h1>Account</h1><p id=who>Signed in as {EMAIL}</p>"
                f"<input id=e value='{EMAIL}'><input id=p type=password value='{PASSWORD}'>"
                "<input id=free value='nothing secret'></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ScreenshotsHideTheLogin(unittest.IsolatedAsyncioTestCase):
    async def test_the_page_is_swapped_for_the_capture_and_restored_after(self):
        from browser import close_browser, open_browser

        trace_safety.forget_secrets()
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        import egress
        original = egress.is_blocked_address
        egress.is_blocked_address = lambda address: False if str(address) == "127.0.0.1" else original(address)
        credentials.TestCredentials(EMAIL, PASSWORD).register()
        browser, stagehand, page, guard = await open_browser()
        read = ("(document.body.innerText + ' ' + [...document.querySelectorAll('input')]"
                ".map((i) => i.value).join(' '))")
        try:
            await page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
            before = await page.evaluate(read)
            async with credentials.redacted_page(page):
                during = await page.evaluate(read)
            after = await page.evaluate(read)
        finally:
            egress.is_blocked_address = original
            server.shutdown()
            await close_browser(browser, stagehand, guard)
            trace_safety.forget_secrets()
        self.assertIn(EMAIL, before)
        self.assertIn(PASSWORD, before)
        self.assertNotIn(EMAIL, during)
        self.assertNotIn(PASSWORD, during)
        self.assertIn("[test email]", during)
        self.assertIn("[test password]", during)
        self.assertIn("nothing secret", during, "other values are untouched")
        self.assertIn(EMAIL, after, "the page is put back")
        self.assertIn(PASSWORD, after)


# ----------------------------------------------------------------- the real worker path, end to end

@unittest.skipIf(os.environ.get("SKIP_LIVE_TESTS"), "SKIP_LIVE_TESTS is set")
class EndToEnd(unittest.TestCase):
    reports: dict = {}
    output = ""

    @classmethod
    def setUpClass(cls):
        report = Path(tempfile.gettempdir()) / "first-user-credentials-report.json"
        existing = os.environ.get("CREDENTIALS_REPORT")  # a report from a harness run made earlier, to re-check
        if existing and Path(existing).exists():
            cls.output = ""
            cls.reports = {r["scenario"]: r for r in json.loads(Path(existing).read_text(encoding="utf-8"))}
            return
        report.unlink(missing_ok=True)
        process = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "credentials_harness.py"), str(report)],
            cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        )
        cls.output = process.stdout + process.stderr
        if process.returncode != 0 or not report.exists():
            raise AssertionError(f"the harness failed (exit {process.returncode}):\n{cls.output[-3000:]}")
        cls.reports = {r["scenario"]: r for r in json.loads(report.read_text(encoding="utf-8"))}

    def secrets_in(self, scenario: str) -> list[str]:
        report = self.reports[scenario]
        values = list(report.get("secrets", []))
        # The password the app received during a self sign-up was generated at run time.
        values += [s["password"] for s in report["site_received"]["signups"] if s.get("password")]
        return values

    def places(self, scenario: str) -> dict[str, str]:
        report = self.reports[scenario]
        return {
            "database writes (results, steps, frictions, first impression)": json.dumps(report["db_writes"]),
            "exported spans": "\n".join(report["exported_spans"]),
            "requests to a model": "\n".join(report["model_requests"]),
        }

    def test_no_secret_is_anywhere_it_should_not_be(self):
        for scenario in self.reports:
            secrets_found = self.secrets_in(scenario)
            for place, text in self.places(scenario).items():
                for secret in secrets_found:
                    self.assertNotIn(secret, text, f"{scenario}: a secret is in {place}")
        for secret in (PASSWORD, EMAIL):
            self.assertNotIn(secret, self.output, "a test login is in the process's own output")
        for scenario in self.reports:
            for secret in self.secrets_in(scenario):
                self.assertNotIn(secret, self.output, f"{scenario}: a secret is in the process's output")

    def test_no_script_sent_into_a_page_holds_a_secret(self):
        # Scripts run in the page's own world, which the page can watch. Secrets reach a page only
        # by being typed into the field they belong to (Stagehand variables or a local fill).
        for scenario, report in self.reports.items():
            sent = "\n".join(report["page_scripts"])
            self.assertGreater(len(report["page_scripts"]), 5, scenario)
            for secret in [*self.secrets_in(scenario), EMAIL, PASSWORD, "Other-Tenant-Pw-9911!"]:
                self.assertNotIn(secret, sent, f"{scenario}: a secret was sent into a page as part of a script")

    def test_the_database_holds_no_login_after_every_run(self):
        for scenario, report in self.reports.items():
            self.assertEqual(report["secrets_left_in_database"], {}, scenario)

    def test_screenshots_were_taken_with_the_login_hidden(self):
        probes = [p for r in self.reports.values() for p in r["page_probes"]]
        self.assertGreater(len(probes), 0)
        self.assertFalse(any(p["shows_a_secret"] for p in probes))

    def test_a_provided_login_was_typed_into_the_site_and_never_seen_by_a_model(self):
        report = self.reports["test_login"]
        logins = report["site_received"]["logins"]
        self.assertEqual(len(logins), 1)
        self.assertTrue(logins[0]["password_ok"], "the site received the right email and password")
        result = self.final_result("test_login")
        self.assertEqual(result["entry"]["test_login"], "used")
        self.assertEqual(result["entry"]["start_link"], report["start_url"])
        steps = [w["tool"] for w in report["db_writes"] if w["kind"] == "step"]
        self.assertIn("sign_in", steps)
        # The page showed the email, so the lookup model's request had to be scrubbed.
        self.assertIn("[test email]", "\n".join(report["model_requests"]))

    def test_self_signup_uses_a_generated_identity(self):
        report = self.reports["self_signup"]
        signups = report["site_received"]["signups"]
        self.assertEqual(len(signups), 1)
        signup = signups[0]
        self.assertRegex(signup["email"], r"^first\.user\.[0-9a-f]{8}@example\.com$")
        self.assertEqual(signup["password"], signup["confirm"])
        self.assertGreaterEqual(len(signup["password"]), 14)
        result = self.final_result("self_signup")
        self.assertEqual(result["entry"]["self_signup"], "used")
        self.assertEqual(result["entry"]["created_account_email"], signup["email"])

    def test_email_verification_ends_the_run_as_blocked(self):
        result = self.final_result("needs_verification")
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["stopped_by"], "sign_up_needs_verification")
        self.assertEqual(result["entry"]["self_signup"], "blocked_verification")
        self.assertEqual(result["entry"]["diagnosis"]["result"], "needs_verification")
        self.assertEqual(result["entry"]["diagnosis"]["challenge"], "email_verification")
        self.assertTrue(result["entry"]["blocked_at_login"])
        self.assertIn("sent by email", result["reason"])

    # --- the sign-in diagnosis: signed in, rejected, needs verification or no effect

    def sign_in_steps(self, scenario: str) -> list[dict]:
        return [w for w in self.reports[scenario]["db_writes"] if w["kind"] == "step" and w["tool"] == "sign_in"]

    def test_a_rejected_login_is_quoted_with_the_status_and_not_retried(self):
        report = self.reports["wrong_password"]
        result = self.final_result("wrong_password")
        diagnosis = result["entry"]["diagnosis"]
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["stopped_by"], "sign_in_rejected")
        self.assertEqual(diagnosis["result"], "rejected")
        self.assertEqual(diagnosis["page_message"], "Invalid email or password")
        self.assertIn("401", diagnosis["http_statuses"])
        self.assertIn("Invalid email or password", result["reason"])
        self.assertIn("401", result["reason"])
        # The same credentials were sent once, and the evidence points at the step that did it.
        self.assertEqual(len(report["site_received"]["logins"]), 1)
        self.assertEqual(len(self.sign_in_steps("wrong_password")), 1)
        self.assertEqual(diagnosis["step"], self.sign_in_steps("wrong_password")[0]["idx"])
        self.assertTrue(result["entry"]["blocked_at_login"])

    def test_a_captcha_after_the_login_is_needs_verification(self):
        result = self.final_result("captcha")
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["stopped_by"], "sign_in_needs_verification")
        self.assertEqual(result["entry"]["diagnosis"]["challenge"], "captcha")
        self.assertIn("CAPTCHA", result["reason"])
        self.assertEqual(len(self.sign_in_steps("captcha")), 1)

    def test_a_two_factor_prompt_after_the_login_is_needs_verification(self):
        result = self.final_result("two_factor")
        self.assertEqual(result["stopped_by"], "sign_in_needs_verification")
        self.assertEqual(result["entry"]["diagnosis"]["challenge"], "two_factor")
        self.assertIn("two-factor", result["reason"])
        self.assertEqual(len(self.sign_in_steps("two_factor")), 1)

    def test_a_login_with_no_effect_is_tried_once_more_and_then_blocked(self):
        result = self.final_result("no_effect")
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["stopped_by"], "sign_in_no_effect")
        self.assertEqual(result["entry"]["diagnosis"]["result"], "no_effect")
        self.assertLessEqual(len(self.sign_in_steps("no_effect")), 2, "the same credentials, never more than twice")

    def test_a_login_printed_on_the_page_is_reported_as_such(self):
        result = self.final_result("page_login")
        self.assertEqual(result["entry"]["page_login"], "shown_on_page")
        self.assertEqual(result["entry"]["test_login"], "not_provided")
        self.assertEqual(result["entry"]["access_mode"], "link")

    def test_third_party_only_ends_blocked_and_names_the_options(self):
        report = self.reports["third_party_only"]
        result = self.final_result("third_party_only")
        self.assertEqual(result["outcome"], "blocked")
        self.assertTrue(result["entry"]["blocked_at_login"])
        self.assertIn("Google", result["reason"])
        self.assertIn("GitHub", result["reason"])
        self.assertEqual(report["site_received"]["logins"], [])
        self.assertEqual(report["site_received"]["signups"], [])

    def test_every_finding_points_at_a_step_that_exists(self):
        for scenario, report in self.reports.items():
            result = self.final_result(scenario)
            steps = {w["idx"] for w in report["db_writes"] if w["kind"] == "step"}
            findings = result.get("findings")
            self.assertIsNotNone(findings, f"{scenario}: the report writer produced no list")
            self.assertLessEqual(len(findings), 5, scenario)
            for finding in findings:
                self.assertIn(finding["evidence"]["step"], steps, f"{scenario}: {finding['title']}")
                self.assertIn(finding["kind"], ("site_problem", "unclear_wording", "hidden_error"))
                self.assertIn(finding["severity"], ("high", "medium", "low"))
                self.assertTrue(finding["fix_prompt"] and finding["reproduce"] and finding["happened"])

    def test_the_report_writer_ran_as_its_own_span(self):
        # Spans are exported in batches, so one can land in the next scenario's slice: count them all.
        names = [json.loads(span).get("name") for report in self.reports.values()
                 for span in report["exported_spans"]]
        self.assertGreaterEqual(names.count("report_writer"), len(self.reports))

    def test_every_run_has_a_first_impression(self):
        for scenario, report in self.reports.items():
            reviews = [w["review"] for w in report["db_writes"] if w["kind"] == "first_impression"]
            self.assertEqual(len(reviews), 1, scenario)
            review = reviews[0]
            self.assertEqual(
                set(review), {"what_it_does", "who_its_for", "main_action", "hesitations", "suggestions"})
            self.assertLessEqual(len(review["suggestions"]), 3)
            self.assertLessEqual(len(review["hesitations"]), 4)
            self.assertIn(review["what_it_does"]["clear"], ("yes", "partly", "no"))
            self.assertTrue(review["what_it_does"]["summary"])
            self.assertEqual(self.final_result(scenario)["first_impression"], review)

    def final_result(self, scenario: str) -> dict:
        saved = [w for w in self.reports[scenario]["db_writes"] if w["kind"] in ("finish_run", "fail_run")]
        self.assertEqual(len(saved), 1, scenario)
        return saved[0]["result"]


if __name__ == "__main__":
    unittest.main()
