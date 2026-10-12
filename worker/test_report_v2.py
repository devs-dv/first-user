"""Report v2: the verdict, the success condition, run facts, evidence bases and structured fix prompts.

No browser and no network: a stand-in model and run context. Live behaviour (a real visit producing
a verdict and facts) is checked by running a visit directly, see hackathon.md.
"""

import asyncio
import re
import unittest
from unittest import mock

import browse
import claims
import config
import report_writer
import verdict as verdict_module
from run_facts import build_run_facts
from test_report_writer import FakeClient, finding, make_ctx
from tools import RunContext

URL = "https://shop.test/"

VERIFIED = {"verdict": "verified", "reason": "The cart lists the mug at quantity 1 after the Add click."}
UNVERIFIED = {"verdict": "unverified", "reason": "No before-state was recorded, so the colour change cannot be seen."}
CONTRADICTED = {"verdict": "contradicted", "reason": "The cart is empty.", "contradicting_evidence": "Cart (0 items)"}


def entry(**overrides) -> dict:
    base = {"test_login": "not_provided", "self_signup": "not_used", "login_wall_seen": False,
            "page_login": "not_used", "blocked_at_login": False, "diagnosis": None, "bot_check": None}
    base.update(overrides)
    return base


def compute(**overrides) -> dict:
    args = dict(outcome="achieved", stopped_by="finish", reason="Done.", verification=VERIFIED, entry=entry(),
                own_issue_steps=[], site_friction_count=0, page_error_count=0, last_step=9,
                last_step_url=URL + "cart", site_evidence=None)
    args.update(overrides)
    return verdict_module.compute_verdict(**args)


class VerdictKinds(unittest.TestCase):
    def test_got_through_is_achieved_and_verified(self):
        v = compute()
        self.assertEqual(v["kind"], "got_through")
        self.assertEqual(v["headline"], "A first-time visitor got through")
        self.assertEqual(v["evidence_quote"], VERIFIED["reason"])
        self.assertEqual(v["basis"], "verified")

    def test_unconfirmed_says_what_the_check_could_not_see(self):
        v = compute(outcome="achieved_unconfirmed", verification=UNVERIFIED)
        self.assertEqual(v["kind"], "unconfirmed")
        self.assertIn("could not confirm", v["headline"])
        self.assertIn("cannot be seen", v["detail"])
        self.assertEqual(v["evidence_quote"], UNVERIFIED["reason"])
        self.assertEqual(v["basis"], "observed")
        # An old run saved as "unverified" reads the same.
        self.assertEqual(compute(outcome="unverified", verification=UNVERIFIED)["kind"], "unconfirmed")

    def test_stuck_names_the_page_and_the_step(self):
        for outcome in ("blocked", "gave_up", "max_steps"):
            v = compute(outcome=outcome, verification=None, reason="The cart never updated.",
                        site_friction_count=1, site_evidence=(6, "cart stays at 0 items"),
                        last_step=7, last_step_url=URL + "checkout")
            self.assertEqual(v["kind"], "stuck", outcome)
            self.assertEqual(v["headline"], "A first-time visitor got stuck on shop.test/checkout")
            self.assertEqual(v["where_step"], 6, "the step of the site's own evidence")
            self.assertEqual(v["evidence_quote"], "cart stays at 0 items")

    def test_a_contradicted_claim_is_stuck_and_verified(self):
        v = compute(outcome="not_achieved", verification=CONTRADICTED, reason="The agent said it was done.")
        self.assertEqual(v["kind"], "stuck")
        self.assertEqual(v["basis"], "verified")
        self.assertEqual(v["evidence_quote"], "Cart (0 items)")

    def test_login_wall_carries_the_three_ways_in(self):
        v = compute(outcome="blocked", verification=None, entry=entry(blocked_at_login=True, diagnosis={
            "stage": "sign_in", "result": "rejected", "step": 4, "url": URL + "login",
            "page_message": "Invalid email or password"}))
        self.assertEqual(v["kind"], "login_wall")
        self.assertEqual(len(v["ways_in"]), 3)
        self.assertIn("demo or guest link", v["ways_in"][0])
        self.assertIn("test account", v["ways_in"][1])
        self.assertIn("sign up by itself", v["ways_in"][2])
        self.assertEqual(v["where_step"], 4)
        self.assertEqual(v["evidence_quote"], "Invalid email or password")

    def test_bot_check_is_its_own_kind(self):
        v = compute(outcome="blocked", stopped_by="bot_check", verification=None,
                    entry=entry(bot_check={"phrase": "Verify you are human", "url": URL, "step": 1}))
        self.assertEqual(v["kind"], "bot_check")
        self.assertEqual(v["where_step"], 1)
        self.assertEqual(v["evidence_quote"], "Verify you are human")
        self.assertIn("nothing is said about the site", v["detail"])

    def test_our_failure_covers_errors_and_our_tool_with_no_sign_of_the_site(self):
        for kwargs in (
            dict(outcome="error", stopped_by="api_error", verification=None, reason="Anthropic API error"),
            dict(outcome="error", stopped_by="refusal", verification=None),
            dict(outcome="blocked", verification=None, own_issue_steps=[7, 8], last_step=8,
                 reason="Clicking Start had no effect."),
        ):
            v = compute(**kwargs)
            self.assertEqual(v["kind"], "our_failure", kwargs)
            self.assertIn("nothing about your site", v["headline"].replace("says nothing about your site",
                                                                           "nothing about your site"))

    def test_our_issues_alongside_real_site_evidence_are_not_our_failure(self):
        # The saucedemo problem_user run: our tool had issues, and the site really breaks.
        v = compute(outcome="blocked", verification=None, own_issue_steps=[7, 9], last_step=10,
                    site_friction_count=1, site_evidence=(10, "Last Name stays empty"))
        self.assertEqual(v["kind"], "stuck")
        v = compute(outcome="blocked", verification=None, own_issue_steps=[7, 9], last_step=10,
                    page_error_count=2)
        self.assertEqual(v["kind"], "stuck")

    def test_every_kind_is_one_of_the_six_and_has_a_basis(self):
        for v in (compute(), compute(outcome="achieved_unconfirmed", verification=UNVERIFIED),
                  compute(outcome="gave_up", verification=None), compute(outcome="error", stopped_by="api_error")):
            self.assertIn(v["kind"], verdict_module.KINDS)
            self.assertIn(v["basis"], ("observed", "verified"))
            self.assertTrue(v["headline"])


class RunVerdictFromAContext(unittest.TestCase):
    def ctx(self):
        ctx = make_ctx()
        ctx.entry.update(entry())
        return ctx

    def test_browse_builds_the_verdict_from_the_run(self):
        ctx = self.ctx()
        finished = {"outcome": "blocked", "stopped_by": "finish", "reason": "The cart stayed empty."}
        v = browse._verdict(ctx, finished, None, browse._entry_summary(ctx, finished))
        self.assertEqual(v["kind"], "stuck")
        self.assertEqual(v["where_step"], 6, "the visitor's noted problem")
        self.assertIn("shop.test", v["headline"])


class NoSiteFindingsFromAnotherThingsFailure(unittest.TestCase):
    FINISHED = {"outcome": "blocked", "stopped_by": "finish", "reason": "Nothing worked."}

    def run_writer(self, verdict, finished=None):
        client = FakeClient([finding()])
        ctx = make_ctx()
        with mock.patch.object(report_writer, "AsyncAnthropic", lambda: client), \
                mock.patch.object(report_writer.neatlogs, "wrap", lambda c: c):
            result = asyncio.run(report_writer.write_findings(ctx, finished or self.FINISHED, None, verdict))
        return result, client

    def test_our_failure_and_bot_check_produce_no_findings_and_no_model_call(self):
        for kind in ("our_failure", "bot_check"):
            result, client = self.run_writer({"kind": kind})
            self.assertEqual(result, [], kind)
            self.assertEqual(client.sent, [], f"{kind}: the model was not asked")

    def test_a_bot_check_stop_alone_is_enough(self):
        result, client = self.run_writer(None, {"outcome": "blocked", "stopped_by": "bot_check", "reason": "x"})
        self.assertEqual(result, [])
        self.assertEqual(client.sent, [])

    def test_a_stuck_visit_still_gets_findings(self):
        result, client = self.run_writer({"kind": "stuck"})
        self.assertEqual(len(result), 1)
        self.assertEqual(len(client.sent), 1)


class FixPromptsAlwaysHaveCriteria(unittest.TestCase):
    def build(self, **overrides):
        item = finding(**overrides)
        return report_writer.build_findings([item], make_ctx())

    def test_a_prompt_has_every_part_in_order(self):
        [f] = self.build(acceptance_criteria=["The cart badge reads 1 after Add to cart.",
                                              "An error appears when the request fails.",
                                              "The Add button works a second time."])
        prompt = f["fix_prompt"]
        order = ["Observed issue", "Expected behaviour", "What to change", "Constraints", "Acceptance criteria", "Retest"]
        positions = [prompt.index(part) for part in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("step 3, page https://shop.test/products, screenshot https://img/3.png", prompt)
        self.assertIn("Keep existing validation and business rules.", prompt)
        self.assertIn("No unrelated redesigns.", prompt)
        self.assertIn("Change nothing that works.", prompt)
        self.assertIn(report_writer.RETEST, prompt)
        self.assertIn("Report Not reached if the relevant state cannot be reached; do not report Fixed without "
                      "testing it.", prompt)

    def test_criteria_are_always_three_to_five(self):
        for given in ([], ["Only one."], ["a one.", "b two.", "c three.", "d four.", "e five.", "f six.", "g seven."],
                      None, "not a list", [None, 3, ""]):
            [f] = self.build(acceptance_criteria=given)
            criteria = f["acceptance_criteria"]
            self.assertTrue(3 <= len(criteria) <= 5, (given, criteria))
            numbered = re.findall(r"(?m)^(\d+)\. ", f["fix_prompt"].split("Acceptance criteria")[1])
            self.assertEqual(len(numbered), len(criteria))

    def test_added_criteria_restate_the_finding_and_are_checkable(self):
        [f] = self.build(acceptance_criteria=[])
        joined = " ".join(f["acceptance_criteria"])
        self.assertIn("/products", joined)
        self.assertIn("step 3", joined)
        self.assertIn("/api/cart", joined, "the page error is named when there is one")

    def test_no_test_code_and_no_promised_outcomes(self):
        [f] = self.build(
            fix_prompt="Show an error on /products when the cart request fails. This will increase conversions by "
                       "20% and boost sales.",
            acceptance_criteria=["The cart error is visible.", "Conversion rises 15%.", "Add to cart works again."])
        text = f["fix_prompt"]
        self.assertNotRegex(text, r"(?i)conversion|boost|\d+\s?%|will increase")
        self.assertNotRegex(text, r"(?i)\bassert\b|def test_|describe\(|expect\(")
        self.assertEqual(len(f["acceptance_criteria"]), 3)
        self.assertIn("Show an error on /products when the cart request fails.", text)

    def test_the_basis_of_each_part_is_stated(self):
        [f] = self.build()
        self.assertEqual(f["basis"], "observed")
        self.assertEqual(f["fix_basis"], "recommendation")

    def test_the_old_format_returns_when_the_flag_is_off(self):
        with mock.patch.object(report_writer, "REPORT_V2", False):
            [f] = self.build()
        self.assertNotIn("Acceptance criteria", f["fix_prompt"])
        self.assertIn("Context, from an automated first-visit test", f["fix_prompt"])


class RecommendationsNeverPromise(unittest.TestCase):
    def test_promising_sentences_are_removed(self):
        self.assertEqual(
            claims.strip_promises("Add a screenshot above the fold. This will increase sign-ups by 30%."),
            "Add a screenshot above the fold.")
        self.assertEqual(claims.strip_promises("Boost conversion with a bigger button."), "")
        self.assertEqual(claims.strip_promises("Name the audience in the headline."),
                         "Name the audience in the headline.")
        self.assertEqual(claims.strip_promises(""), "")

    def test_first_impression_suggestions_pass_through_it(self):
        import first_impression

        out = first_impression.normalise({
            "what_it_does": {"clear": "yes", "summary": "x"}, "who_its_for": {"clear": "yes", "summary": "x"},
            "main_action": {"obvious": "yes", "summary": "x"}, "hesitations": [],
            "suggestions": ["Name the audience in the headline.", "Make the button red to lift conversion by 12%."]})
        self.assertEqual(out["suggestions"], ["Name the audience in the headline."])


class SuccessCondition(unittest.TestCase):
    def test_the_verifier_is_asked_to_judge_the_condition(self):
        import verifier

        class Page:
            async def evaluate(self, js):
                return "[]" if "querySelectorAll" in js else "Project Apollo"

            async def url(self):
                return URL + "dashboard"

            async def title(self):
                return "Dashboard"

            async def screenshot(self, **kwargs):
                return b"\x89PNG\r\n\x1a\n"

        sent = []

        class Client:
            def __init__(self):
                self.messages = type("M", (), {"create": self.create})()

            async def create(self, **kwargs):
                sent.append(kwargs)
                block = type("B", (), {"type": "tool_use", "input": {
                    "verdict": "verified", "reason": "Apollo is listed.", "contradicting_evidence": ""}})()
                usage = type("U", (), {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0,
                                       "cache_read_input_tokens": 0})()
                return type("R", (), {"content": [block], "usage": usage, "model": "claude-haiku-5-5"})()

            async def close(self):
                pass

        record = [{"step": 1, "tool": "look", "url": URL, "summary": "Dashboard.", "interactive": []}]
        with mock.patch.object(verifier, "AsyncAnthropic", Client), mock.patch.object(verifier.neatlogs, "wrap",
                                                                                      lambda c: c):
            asyncio.run(verifier.verify("Create a project", record, Page(), None, None,
                                        success_condition="a project appears in the dashboard"))
            asyncio.run(verifier.verify("Create a project", record, Page(), None, None))
        with_condition = " ".join(b["text"] for b in sent[0]["messages"][0]["content"] if b["type"] == "text")
        without = " ".join(b["text"] for b in sent[1]["messages"][0]["content"] if b["type"] == "text")
        self.assertIn("Success condition given by the founder: a project appears in the dashboard", with_condition)
        self.assertIn("THIS condition", with_condition)
        self.assertNotIn("Success condition", without)

    def test_the_writer_and_the_facts_say_when_none_was_given(self):
        ctx = make_ctx()
        text = report_writer._entry_lines(ctx, {"outcome": "achieved", "reason": "ok"}, None)
        self.assertIn("No success condition was given: the goal was checked as worded.", text)
        ctx.success_condition = "a project appears in the dashboard"
        text = report_writer._entry_lines(ctx, {"outcome": "achieved", "reason": "ok"}, None)
        self.assertIn("Success condition given by the founder: a project appears in the dashboard", text)
        facts = build_run_facts(ctx, {"outcome": "achieved"}, None, 5)
        self.assertEqual(facts["success_condition"], "a project appears in the dashboard")
        self.assertFalse(facts["checked_without_success_condition"])
        ctx.success_condition = None
        self.assertTrue(build_run_facts(ctx, {"outcome": "achieved"}, None, 5)["checked_without_success_condition"])


class RunFacts(unittest.TestCase):
    def test_facts_are_counted_from_the_run(self):
        ctx = make_ctx()
        ctx.record[1]["rung"] = "b"
        ctx.record[2]["rung"] = "a"
        ctx.page_reloads = 2
        facts = build_run_facts(ctx, {"outcome": "blocked"}, VERIFIED, 8)
        self.assertEqual(facts["steps_taken"], 8)
        self.assertEqual([(r["step"], r["rung"]) for r in facts["recoveries"]], [(2, "b")])
        self.assertEqual([i["step"] for i in facts["own_issues"]], [4])
        self.assertEqual(facts["page_reloads"], 2)
        self.assertEqual(facts["page_errors"], ["request: 500 /api/cart"])
        self.assertEqual(facts["verifier"]["verdict"], "verified")
        self.assertIn("quote", facts["verifier"])
        self.assertIn("cost_usd", facts)
        self.assertGreaterEqual(facts["duration_seconds"], 0)

    def test_the_worker_adds_what_only_it_knows(self):
        import worker_run

        saved = {}

        class FakeDb:
            async def take_run_secrets(self, run_id):
                return None

            async def delete_run_secrets(self, run_id):
                pass

            async def finish_run(self, run_id, result, agent_version, brain_model):
                saved["result"] = result

            async def fail_run(self, *args, **kwargs):
                saved["failed"] = True

            class RunRecorder:
                def __init__(self, run_id):
                    pass

        async def first_visit(*args, **kwargs):
            return {"outcome": "achieved", "steps": 3, "reason": "ok", "trace_id": "abc123",
                    "run_facts": {"steps_taken": 3}}

        fake = FakeDb()
        with mock.patch.multiple(worker_run.db, take_run_secrets=fake.take_run_secrets,
                                 delete_run_secrets=fake.delete_run_secrets, finish_run=fake.finish_run,
                                 fail_run=fake.fail_run, RunRecorder=fake.RunRecorder), \
                mock.patch.object(worker_run, "first_visit", first_visit):
            asyncio.run(worker_run.execute({"id": "r1", "url": URL, "goal": "g", "worker_id": "ip-10@abc"}, "abc"))
        facts = saved["result"]["run_facts"]
        self.assertEqual(facts["agent_version"], "abc")
        self.assertEqual(facts["worker_id"], "ip-10@abc")
        self.assertEqual(facts["trace_id"], "abc123")

    def test_the_run_row_gets_the_verdict_and_the_facts(self):
        import db

        updates = []

        async def fake_update(run_id, update):
            updates.append(update)

        with mock.patch.object(db, "_update_run", fake_update):
            asyncio.run(db.finish_run("r1", {"outcome": "achieved", "verdict": {"kind": "got_through"},
                                             "run_facts": {"steps_taken": 3}, "usage": {}}, "v", "m"))
        self.assertEqual(updates[0]["verdict"], {"kind": "got_through"})
        self.assertEqual(updates[0]["run_facts"], {"steps_taken": 3})


class TheFlag(unittest.TestCase):
    def test_report_v2_is_on_by_default_and_can_be_turned_off(self):
        self.assertTrue(config.REPORT_V2)
        ctx = RunContext(url=URL, goal="g", run_id="r", stagehand=None, page=None)
        with mock.patch.object(browse, "REPORT_V2", False):
            self.assertTrue(callable(browse._verdict))
        self.assertIsNone(ctx.success_condition)


if __name__ == "__main__":
    unittest.main()
