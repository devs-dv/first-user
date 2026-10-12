"""How the founder lets the visitor in: the form's four choices, as the worker sees them.

No browser and no model: the run row, the prompt text and the refusal of sign_up are checked with
stand-ins.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)
import asyncio
import unittest
from unittest import mock

import auth_tools
import browse
import worker_run
from tools import RunContext, current_run


class AccessModeFromARow(unittest.TestCase):
    def test_a_chosen_mode_wins(self):
        for mode in ("public", "link", "account", "signup"):
            self.assertEqual(worker_run.access_mode_for({"access_mode": mode}), mode)

    def test_a_mode_chosen_on_the_form_is_not_overridden_by_other_fields(self):
        row = {"access_mode": "public", "start_url": "https://x.test/demo", "has_test_login": True}
        self.assertEqual(worker_run.access_mode_for(row), "public")

    def test_older_runs_are_read_from_what_they_have(self):
        self.assertEqual(worker_run.access_mode_for({"has_test_login": True}), "account")
        self.assertEqual(worker_run.access_mode_for({"start_url": "https://x.test/demo"}), "link")
        # Before the choice existed, a run with neither meant "may sign up".
        self.assertEqual(worker_run.access_mode_for({}), "signup")
        self.assertEqual(worker_run.access_mode_for({"access_mode": "nonsense"}), "signup")


class TheLabelIsOnlyWhatWasChosen(unittest.TestCase):
    def test_the_fallback_is_not_reported_as_a_choice(self):
        self.assertFalse(worker_run.access_mode_was_chosen({}))
        self.assertFalse(worker_run.access_mode_was_chosen({"access_mode": None}))
        self.assertTrue(worker_run.access_mode_was_chosen({"access_mode": "public"}))
        self.assertTrue(worker_run.access_mode_was_chosen({"access_mode": "signup"}))
        # A start link or a test login implies the way in, so naming it is accurate.
        self.assertTrue(worker_run.access_mode_was_chosen({"start_url": "https://x.test/demo"}))
        self.assertTrue(worker_run.access_mode_was_chosen({"has_test_login": True}))

    def test_the_entry_names_no_mode_when_none_was_chosen(self):
        ctx = make_ctx("signup")
        ctx.access_mode_chosen = False
        finished = {"outcome": "achieved", "stopped_by": "finish", "reason": "ok"}
        self.assertIsNone(browse._entry_summary(ctx, finished)["access_mode"])
        ctx.access_mode_chosen = True
        self.assertEqual(browse._entry_summary(ctx, finished)["access_mode"], "signup")

    def test_the_default_step_limit_is_twenty_and_the_budget_is_still_there(self):
        import config

        self.assertEqual(config.MAX_STEPS, 20)
        self.assertGreater(config.MAX_RUN_COST_USD, 0)
        self.assertGreater(config.MAX_RUN_TOKENS, 0)
        self.assertEqual(browse.check_budget(config.MAX_RUN_TOKENS + 1, 0.0)["ok"], False)
        self.assertEqual(browse.check_budget(0, config.MAX_RUN_COST_USD + 0.01)["ok"], False)
        self.assertEqual(browse.check_budget(1000, 0.01)["ok"], True)


class BlockedAtALoginOnlyWhenItWas(unittest.TestCase):
    def entry(self, **overrides):
        base = {"test_login": "not_provided", "self_signup": "not_used", "login_wall_seen": False,
                "page_login": "not_used", "page_login_worked": False, "diagnosis": None}
        base.update(overrides)
        return base

    BLOCKED = {"outcome": "blocked", "stopped_by": "finish"}

    def test_signed_in_then_blocked_at_checkout_is_not_a_login_block(self):
        # The saucedemo run: the page's own login was accepted, the block came at checkout, and the reason
        # mentions "the password shown on the page".
        finished = {**self.BLOCKED, "reason": "I logged in with the password shown on the page, but checkout "
                                              "stopped at the First Name field."}
        self.assertTrue(browse.blocked_at_login(self.entry(page_login="shown_on_page"), finished),
                        "without a sign that the login worked, the wording says it was a login block")
        entry = self.entry(page_login="shown_on_page", page_login_worked=True)
        self.assertFalse(browse.blocked_at_login(entry, finished))
        self.assertFalse(browse.blocked_at_login(self.entry(test_login="used"), finished))
        self.assertFalse(browse.blocked_at_login(self.entry(self_signup="used"), finished))

    def test_real_login_blocks_still_count(self):
        reason = {"reason": "Needs a login."}
        self.assertTrue(browse.blocked_at_login(self.entry(login_wall_seen=True), {**self.BLOCKED, **reason}))
        self.assertTrue(browse.blocked_at_login(self.entry(test_login="failed"), {**self.BLOCKED, **reason}))
        self.assertTrue(browse.blocked_at_login(self.entry(self_signup="blocked_third_party"),
                                                {**self.BLOCKED, "reason": "Only Google."}))
        self.assertTrue(browse.blocked_at_login(self.entry(diagnosis={"result": "needs_verification"}),
                                                {**self.BLOCKED, "reason": "A CAPTCHA."}))
        self.assertTrue(browse.blocked_at_login(self.entry(), {**self.BLOCKED, "reason": "The page needs a login."}))

    def test_other_outcomes_and_the_egress_guard_are_never_login_blocks(self):
        self.assertFalse(browse.blocked_at_login(self.entry(login_wall_seen=True),
                                                 {"outcome": "gave_up", "stopped_by": "finish", "reason": "login"}))
        self.assertFalse(browse.blocked_at_login(self.entry(login_wall_seen=True),
                                                 {"outcome": "blocked", "stopped_by": "egress_guard", "reason": "x"}))

    def test_a_block_that_does_not_talk_about_a_login_is_not_one(self):
        self.assertFalse(browse.blocked_at_login(
            self.entry(), {**self.BLOCKED, "reason": "The checkout needs a credit card, so I stopped."}))


class TheVisitorIsToldWhatIsAllowed(unittest.TestCase):
    def test_every_mode_has_a_note_and_only_signup_allows_signing_up(self):
        self.assertEqual(set(browse.ACCESS_NOTES), set(worker_run.ACCESS_MODES))
        for mode, note in browse.ACCESS_NOTES.items():
            if mode == "signup":
                self.assertIn("call sign_up", note)
            else:
                self.assertIn("sign_up will refuse", note, mode)
        self.assertIn("no login", browse.ACCESS_NOTES["public"])
        self.assertIn("sign_in", browse.ACCESS_NOTES["account"])


class FakePage:
    async def url(self):
        return "https://app.test/login"


def make_ctx(mode: str) -> RunContext:
    class Metrics:
        total_prompt_tokens = total_completion_tokens = total_inference_time_ms = 0
        total_cached_input_tokens = total_reasoning_tokens = 0

    class Stagehand:
        async def metrics(self):
            return Metrics()

    return RunContext(url="https://app.test", goal="g", run_id="r", stagehand=Stagehand(), page=FakePage(),
                      access_mode=mode)


SCAN = {"has_password": True, "has_identifier": True, "signupish": True, "tagged": [], "submit_text": "Sign up",
        "third_party_options": ["Google"], "page_message": "", "asks_for_verification": False, "form_title": ""}


class SignUpIsRefusedUnlessChosen(unittest.TestCase):
    def call_sign_up(self, mode: str) -> tuple[dict, RunContext]:
        ctx = make_ctx(mode)

        async def run():
            token = current_run.set(ctx)
            try:
                with mock.patch.object(auth_tools, "_active_page", mock.AsyncMock(return_value=FakePage())), \
                        mock.patch.object(auth_tools, "_scan", mock.AsyncMock(return_value=dict(SCAN))), \
                        mock.patch.object(auth_tools.credentials_module, "generate_identity",
                                          side_effect=AssertionError("an account must not be made")):
                    return await auth_tools.sign_up()
            finally:
                current_run.reset(token)

        return asyncio.run(run()), ctx

    def test_other_modes_never_create_an_account(self):
        for mode in ("public", "link", "account"):
            result, ctx = self.call_sign_up(mode)
            self.assertFalse(result["success"], mode)
            self.assertEqual(result["reason"], "signup_not_allowed", mode)
            self.assertEqual(ctx.entry["self_signup"], "not_used", mode)
            self.assertIsNone(ctx.finished, mode)
            self.assertIsNone(ctx.entry["created_account_email"], mode)


if __name__ == "__main__":
    unittest.main()
