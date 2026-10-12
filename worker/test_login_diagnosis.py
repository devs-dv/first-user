"""The sign-in / sign-up diagnosis: signed in, rejected, needs verification, no effect.

Pure functions on plain scan results: no browser and no model. The live scenarios (a wrong
password with a 401, a CAPTCHA, a two-factor prompt, a button that does nothing) are in
test_credentials.py.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)
import asyncio
import unittest
from unittest import mock

import auth_tools
import login_diagnosis as ld
from tools import RunContext, current_run


def scan(**overrides) -> dict:
    base = {"has_password": False, "has_identifier": False, "signupish": False, "tagged": [], "submit_text": "",
            "third_party_options": [], "page_message": "", "asks_for_verification": False, "challenge": "",
            "form_title": ""}
    base.update(overrides)
    return base


BEFORE = scan(has_password=True, has_identifier=True)


def diagnose(after, *, submitted=True, errors=(), before=BEFORE, after_url="https://app.test/app", stage="sign_in"):
    return ld.diagnose(stage=stage, before=before, after=after, submitted=submitted, errors=list(errors),
                       before_url="https://app.test/login", after_url=after_url, step=4)


class FourResults(unittest.TestCase):
    def test_form_gone_and_no_error_is_signed_in(self):
        d = diagnose(scan())
        self.assertEqual(d["result"], "signed_in")
        self.assertEqual(d["step"], 4)

    def test_form_still_there_with_a_message_is_rejected_and_quotes_it(self):
        d = diagnose(scan(has_password=True, page_message="Invalid email or password"),
                     after_url="https://app.test/login")
        self.assertEqual(d["result"], "rejected")
        self.assertEqual(d["page_message"], "Invalid email or password")
        self.assertIn('"Invalid email or password"', ld.describe(d))

    def test_401_and_403_are_quoted_whether_or_not_there_is_a_message(self):
        d = diagnose(scan(has_password=True, page_message="Wrong password"), errors=[
            "request: 401 https://app.test/api/login", "request: 500 https://app.test/api/other"])
        self.assertEqual(d["http_statuses"], ["401"])
        self.assertIn("401", ld.describe(d))
        d = diagnose(scan(), errors=["request: 403 https://app.test/api/session"])
        self.assertEqual(d["result"], "rejected", "a 403 with the form gone is still a rejection")
        self.assertEqual(d["http_statuses"], ["403"])

    def test_an_error_message_with_the_form_replaced_is_rejected(self):
        d = diagnose(scan(page_message="Login failed: account locked"))
        self.assertEqual(d["result"], "rejected")

    def test_a_neutral_alert_does_not_make_a_rejection(self):
        d = diagnose(scan(page_message="Welcome back, Sam"))
        self.assertEqual(d["result"], "signed_in")

    def test_challenges_are_needs_verification(self):
        for kind, text in (("captcha", "a CAPTCHA"), ("two_factor", "a two-factor code"),
                           ("email_verification", "a code or link sent by email")):
            d = diagnose(scan(challenge=kind))
            self.assertEqual(d["result"], "needs_verification", kind)
            self.assertEqual(d["challenge"], kind)
            self.assertIn(text, ld.describe(d))

    def test_a_challenge_that_was_already_on_the_page_is_not_new(self):
        before = scan(has_password=True, has_identifier=True, challenge="captcha")
        d = diagnose(scan(), before=before)
        self.assertEqual(d["result"], "signed_in")
        self.assertIsNone(d["challenge"])

    def test_a_challenge_outranks_a_401(self):
        d = diagnose(scan(challenge="captcha"), errors=["request: 401 https://app.test/api/login"])
        self.assertEqual(d["result"], "needs_verification")

    def test_nothing_changed_and_nothing_said_is_no_effect(self):
        d = diagnose(scan(has_password=True), submitted=False, after_url="https://app.test/login")
        self.assertEqual(d["result"], "no_effect")
        self.assertIn("no effect", ld.describe(d))

    def test_a_form_that_stays_after_the_page_changed_is_a_rejection_without_a_message(self):
        d = diagnose(scan(has_password=True), submitted=True, after_url="https://app.test/login")
        self.assertEqual(d["result"], "rejected")
        self.assertIn("no message", ld.describe(d))

    def test_a_form_that_could_not_be_filled_in_is_no_effect_with_its_own_reason(self):
        d = ld.diagnose(stage="sign_in", before=BEFORE, after=BEFORE, submitted=False, errors=[],
                        before_url="u", after_url="u", step=2, detail="the test login could not be entered.")
        self.assertEqual(d["result"], "no_effect")
        self.assertIn("could not be entered", ld.describe(d))

    def test_every_result_is_one_of_the_four(self):
        for after in (scan(), scan(has_password=True), scan(challenge="captcha"), scan(page_message="error")):
            self.assertIn(diagnose(after)["result"], ld.RESULTS)


class Fake:
    """A page and a Stagehand that do only what sign_in's submit and diagnosis need."""

    def __init__(self, after: dict, errors: list[str], submitted: bool = True):
        self.after, self.errors, self.submitted = after, errors, submitted


class ToolRules(unittest.TestCase):
    def ctx(self):
        class Metrics:
            total_prompt_tokens = total_completion_tokens = total_inference_time_ms = 0
            total_cached_input_tokens = total_reasoning_tokens = 0

        class Stagehand:
            async def metrics(self):
                return Metrics()

        class Page:
            async def url(self):
                return "https://app.test/login"

        return RunContext(url="https://app.test", goal="g", run_id="r", stagehand=Stagehand(), page=Page())

    def conclude(self, ctx, diagnosis):
        return auth_tools._conclude(
            ctx, stage="sign_in", tool="sign_in", diagnosis=diagnosis, url="https://app.test/login", fields=["email"],
            errors=[], shot=None, changed=True, signed_in_message="in")

    def test_a_rejection_ends_the_run_as_blocked_with_the_reason_and_evidence(self):
        ctx = self.ctx()
        d = diagnose(scan(has_password=True, page_message="Invalid email or password"),
                     errors=["request: 401 https://app.test/api/login"], after_url="https://app.test/login")
        result = self.conclude(ctx, d)
        self.assertFalse(result["success"])
        self.assertEqual(ctx.finished["outcome"], "blocked")
        self.assertEqual(ctx.finished["stopped_by"], "sign_in_rejected")
        self.assertIn("Invalid email or password", ctx.finished["reason"])
        self.assertIn("401", ctx.finished["reason"])
        self.assertEqual(ctx.finished["evidence"]["step"], 4)
        self.assertEqual(ctx.finished["evidence"]["http_statuses"], ["401"])
        self.assertEqual(ctx.entry["test_login"], "failed")

    def test_no_effect_gets_one_retry_and_then_blocks(self):
        ctx = self.ctx()
        d = diagnose(scan(has_password=True), submitted=False, after_url="https://app.test/login")
        first = self.conclude(ctx, d)
        self.assertIsNone(ctx.finished, "one more try is allowed")
        self.assertEqual(first["reason"], "no_effect")
        self.assertIsNone(auth_tools._already_tried(ctx, "sign_in", "sign_in", "u"))
        self.conclude(ctx, d)
        self.assertEqual(ctx.finished["stopped_by"], "sign_in_no_effect")

    def test_a_rejected_login_is_never_typed_again(self):
        ctx = self.ctx()
        d = diagnose(scan(has_password=True, page_message="Invalid password"), after_url="https://app.test/login")
        self.conclude(ctx, d)
        refusal = auth_tools._already_tried(ctx, "sign_in", "sign_in", "https://app.test/login")
        self.assertIsNotNone(refusal)
        self.assertEqual(refusal["reason"], "already_tried")

    def test_never_more_than_one_retry(self):
        ctx = self.ctx()
        ctx.entry["auth_attempts"] = {"sign_in": 2}
        self.assertIsNotNone(auth_tools._already_tried(ctx, "sign_in", "sign_in", "u"))
        ctx.entry["auth_attempts"] = {"sign_in": 1}
        self.assertIsNone(auth_tools._already_tried(ctx, "sign_in", "sign_in", "u"))

    def test_a_signed_in_result_clears_the_login_wall(self):
        ctx = self.ctx()
        ctx.entry["login_wall_seen"] = True
        result = self.conclude(ctx, diagnose(scan()))
        self.assertTrue(result["success"])
        self.assertEqual(ctx.entry["test_login"], "used")
        self.assertFalse(ctx.entry["login_wall_seen"])
        self.assertIsNone(ctx.finished)


if __name__ == "__main__":
    unittest.main()
