"""How the founder lets the visitor in: the form's four choices, as the worker sees them.

No browser and no model: the run row, the prompt text and the refusal of sign_up are checked with
stand-ins.
"""

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
