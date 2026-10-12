"""Check again: the labels, the guided pass and what a retest may take from its original.

No browser and no network: recorded steps and stand-in tools. The original run is the saucedemo
problem_user checkout (the Last Name field loses the typed text).
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)
import asyncio
import unittest
from unittest import mock

import retest
from retest import (build_plans, compare_verdicts, instruction_similar, judge, label_findings, page_key,
                    same_error)

START = "https://www.saucedemo.com/"
CHECKOUT = START + "checkout-step-one.html"


def step(idx, tool, instruction=None, url=START, **result):
    return {"idx": idx, "tool": tool, "input": {"instruction": instruction} if instruction else {},
            "result": result, "url": url}


ORIGINAL_STEPS = [
    step(1, "look", url=START),
    step(2, "do", "type 'problem_user' into the Username field", success=True, changed=True),
    step(3, "do", "click the Login button", url=START + "inventory.html", success=True, changed=True),
    step(4, "do", "click Add to cart for the backpack", url=START + "inventory.html", success=True, changed=True),
    step(5, "do", "click the Checkout button", url=CHECKOUT, success=True, changed=True),
    step(6, "do", "type 'User' into the Last Name textbox", url=CHECKOUT, success=True, changed=True,
         field={"label": "Last Name", "value": "", "contains_typed_text": False}),
    step(7, "look", url=CHECKOUT),
    step(8, "note_friction", url=CHECKOUT),
]


def old_finding(**overrides):
    base = {"title": "Last Name field loses the typed text", "kind": "site_problem", "severity": "high",
            "happened": "Typing 'User' into Last Name left the field empty and put it into First Name.",
            "evidence": {"step": 7, "url": CHECKOUT, "page_errors": [], "quote": None}}
    base.update(overrides)
    return base


def record_entry(step_no, tool="do", instruction="type 'User' into the Last Name field", url_after=CHECKOUT, **extra):
    entry = {"step": step_no, "tool": tool, "url_after": url_after, "url": url_after}
    if tool == "do":
        entry.update(instruction=instruction, page_changed=True)
    entry.update(extra)
    return entry


def labels(plans, findings, record, *, own=(), texts=None, new=(), guided=None):
    return label_findings(plans, findings, record=record, own_issue_steps=set(own), page_texts=texts or {},
                          new_findings=list(new), guided=guided or {})


class Plans(unittest.TestCase):
    def test_the_route_and_the_acting_step_come_from_the_recorded_steps(self):
        [plan] = build_plans([old_finding()], ORIGINAL_STEPS, START)
        self.assertEqual(plan["acting_idx"], 6)
        self.assertEqual(plan["acting_instruction"], "type 'User' into the Last Name textbox")
        self.assertEqual([r["idx"] for r in plan["route"]], [2, 3, 4, 5])
        self.assertEqual(plan["route"][3]["url"], CHECKOUT)
        self.assertEqual(plan["target_page"], "www.saucedemo.com/checkout-step-one.html")
        self.assertTrue(plan["signature"]["field_bad"])
        self.assertIsNone(plan["route_error"])

    @staticmethod
    def with_inserted(row):
        """The original steps with `row` placed (as step 5) before the checkout, and the later ones renumbered."""
        shifted = [{**r, "idx": r["idx"] + 1} if r["idx"] >= 5 else r for r in ORIGINAL_STEPS]
        return sorted(shifted + [{**row, "idx": 5}], key=lambda r: r["idx"])

    def test_attempts_that_did_nothing_are_not_part_of_the_route(self):
        steps = self.with_inserted(step(0, "do", "click the cart icon", success=False, changed=False))
        [plan] = build_plans([old_finding(evidence={"step": 8, "url": CHECKOUT})], steps, START)
        self.assertNotIn(5, [r["idx"] for r in plan["route"]])
        self.assertEqual(len(plan["route"]), 4)

    def test_a_route_that_used_back_is_not_replayed(self):
        steps = self.with_inserted(step(0, "go_back", url=START + "inventory.html"))
        [plan] = build_plans([old_finding(evidence={"step": 8, "url": CHECKOUT})], steps, START)
        self.assertIn("Back", plan["route_error"])

    def test_a_wording_finding_carries_its_quote(self):
        finding = old_finding(kind="unclear_wording", evidence={"step": 7, "url": CHECKOUT, "quote": "Select SKU"})
        [plan] = build_plans([finding], ORIGINAL_STEPS, START)
        self.assertEqual(plan["signature"]["quote"], "Select SKU")


class TheFiveLabels(unittest.TestCase):
    def setUp(self):
        self.findings = [old_finding()]
        self.plans = build_plans(self.findings, ORIGINAL_STEPS, START)

    def only(self, **kwargs):
        return labels(self.plans, self.findings, **kwargs)["labels"][0]

    def test_fixed_when_reached_and_not_reproduced(self):
        item = self.only(record=[record_entry(9, field_ok=True)])
        self.assertEqual(item["label"], "fixed")
        self.assertEqual(item["pass"], "independent")
        self.assertEqual(item["evidence_step"], 9)
        self.assertIn("kept the typed text", item["reason"])

    def test_still_present_when_reached_and_reproduced(self):
        item = self.only(record=[record_entry(9, field_ok=False)])
        self.assertEqual(item["label"], "still_present")
        self.assertEqual(item["evidence_step"], 9)

    def test_not_reached_is_never_fixed(self):
        item = self.only(record=[record_entry(2, tool="look", url_after=START)])
        self.assertEqual(item["label"], "not_reached")
        self.assertIsNone(item["evidence_step"])
        self.assertIn("unverified", item["reason"])
        self.assertIn("not reported as fixed", item["reason"])

    def test_inconclusive_when_reached_but_the_evidence_does_not_decide(self):
        self.assertEqual(self.only(record=[record_entry(9)])["label"], "inconclusive", "field not read back")
        # Our tool could not carry out the action: that proves nothing about the site.
        item = self.only(record=[record_entry(9, field_ok=True)], own={9})
        self.assertEqual(item["label"], "inconclusive")
        self.assertIn("browser tool", item["reason"])

    def test_new_findings_are_the_ones_not_in_the_original(self):
        new_same = {"title": "Last Name field loses the typed text again", "kind": "site_problem", "severity": "high",
                    "happened": "Typing 'User' into Last Name left the field empty and put it into First Name.",
                    "evidence": {"step": 9, "url": CHECKOUT, "page_errors": []}}
        new_other = {"title": "Cart badge counts the wrong number", "kind": "site_problem", "severity": "medium",
                     "happened": "Two backpacks added, badge reads three.",
                     "evidence": {"step": 4, "url": START + "inventory.html", "page_errors": []}}
        out = labels(self.plans, self.findings, record=[record_entry(9)], new=[new_same, new_other])
        self.assertEqual(out["labels"][0]["label"], "still_present", "the retest's own visit found it again")
        self.assertEqual(out["labels"][0]["pass"], "independent")
        self.assertEqual(out["labels"][0]["evidence_step"], 9)
        self.assertEqual([n["title"] for n in out["new"]], ["Cart badge counts the wrong number"])
        self.assertEqual(out["new"][0]["label"], "new")

    def test_the_guided_pass_labels_what_pass_one_never_reached(self):
        followed = {0: {"followed": True, "observed": {"executed": True, "changed": True, "page_errors": [],
                                                        "field_ok": False}, "evidence_step": 14}}
        item = self.only(record=[], guided=followed)
        self.assertEqual((item["label"], item["pass"], item["evidence_step"]), ("still_present", "guided", 14))
        followed[0]["observed"]["field_ok"] = True
        self.assertEqual(self.only(record=[], guided=followed)["label"], "fixed")
        stopped = {0: {"followed": False, "why": "the flow has changed: that step led to /basket"}}
        item = self.only(record=[], guided=stopped)
        self.assertEqual(item["label"], "not_reached")
        self.assertIn("flow has changed", item["reason"])


class Judging(unittest.TestCase):
    ERR = {"errors": ["js_error: Uncaught TypeError: Cannot read properties of undefined (reading 'value')"],
           "field_bad": False, "quote": None}

    def observed(self, **kw):
        base = {"executed": True, "changed": True, "page_errors": [], "field_ok": None}
        base.update(kw)
        return base

    def test_a_page_error_that_comes_back_is_still_present(self):
        label, _ = judge(self.ERR, self.observed(page_errors=[
            "js_error: Uncaught TypeError: Cannot read properties of undefined (reading 'value')"]))
        self.assertEqual(label, "still_present")

    def test_no_error_and_a_response_is_fixed_but_a_different_error_is_not(self):
        self.assertEqual(judge(self.ERR, self.observed())[0], "fixed")
        self.assertEqual(judge(self.ERR, self.observed(page_errors=["request: 500 /api/other"]))[0], "inconclusive")
        self.assertEqual(judge(self.ERR, self.observed(changed=False))[0], "inconclusive")

    def test_wording_is_judged_on_the_pages_text(self):
        sig = {"errors": [], "field_bad": False, "quote": "Select SKU"}
        self.assertEqual(judge(sig, self.observed(), "Choose a size. Select SKU below")[0], "still_present")
        self.assertEqual(judge(sig, self.observed(), "Choose a size below")[0], "fixed")
        self.assertEqual(judge(sig, self.observed(), None)[0], "inconclusive")

    def test_nothing_measurable_is_inconclusive(self):
        sig = {"errors": [], "field_bad": False, "quote": None}
        self.assertEqual(judge(sig, self.observed())[0], "inconclusive")
        self.assertEqual(judge(self.ERR, None)[0], "inconclusive")

    def test_error_matching_ignores_numbers_and_hosts(self):
        self.assertTrue(same_error("request: 500 https://a.test/api/cart", "request: 503 https://b.test/api/cart"))
        self.assertFalse(same_error("request: 500 https://a.test/api/cart", "js_error: x is not defined"))

    def test_instructions_and_pages(self):
        self.assertTrue(instruction_similar("type 'User' into the Last Name textbox",
                                            "type 'User' into the Last Name field"))
        self.assertFalse(instruction_similar("click the Login button", "type 'User' into the Last Name field"))
        self.assertEqual(page_key("https://Shop.test/cart/?x=1#top"), "shop.test/cart")


class Verdicts(unittest.TestCase):
    def test_before_and_after(self):
        before = {"kind": "stuck", "headline": "A first-time visitor got stuck on shop.test/checkout",
                  "where_step": 6, "where_url": "https://shop.test/checkout"}
        after = {"kind": "got_through", "headline": "A first-time visitor got through", "where_step": 9,
                 "where_url": "https://shop.test/done"}
        out = compare_verdicts(before, after)
        self.assertEqual(out["change"], "improved")
        self.assertEqual(out["summary"],
                         "Before: A first-time visitor got stuck on shop.test/checkout. After: A first-time visitor "
                         "got through.")
        self.assertEqual(compare_verdicts(after, before)["change"], "worse")
        self.assertEqual(compare_verdicts(before, before)["change"], "same")
        self.assertEqual(compare_verdicts(before, {"kind": "bot_check", "headline": "x"})["change"], "not_comparable")
        self.assertEqual(compare_verdicts(None, after)["change"], "not_comparable")


# ----------------------------------------------------------------------------------- the guided pass

class FakeTools:
    """Stands in for tools.do: answers by instruction, and remembers what it was asked."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    async def do(self, instruction):
        self.asked.append(instruction)
        return dict(self.answers.get(instruction, {"success": False, "changed": False, "reason": "failed"}))


class Ctx:
    def __init__(self):
        self.tool_calls = 0
        self.recorder = None
        self.usage = type("U", (), {"total_tokens": 100, "total_cost": 0.001})()
        self.step_shots = {}
        self.page = object()
        self.egress = object()
        self.access_mode = "public"
        self.credentials = None
        self.success_condition = None
        self.url = START


class Browse:
    @staticmethod
    def check_budget(tokens, cost):
        return {"ok": True}


class GuidedPassFollowsTheSameRouteOnly(unittest.TestCase):
    def setUp(self):
        [self.plan] = build_plans([old_finding()], ORIGINAL_STEPS, START)
        route_ok = {
            "type 'problem_user' into the Username field": {"success": True, "changed": True, "url": START},
            "click the Login button": {"success": True, "changed": True, "url": START + "inventory.html"},
            "click Add to cart for the backpack": {"success": True, "changed": True,
                                                   "url": START + "inventory.html"},
            "click the Checkout button": {"success": True, "changed": True, "url": CHECKOUT},
        }
        self.route_ok = route_ok
        self.acting = "type 'User' into the Last Name textbox"

    def replay(self, answers, current=CHECKOUT, plan=None):
        tools = FakeTools(answers)

        async def current_url():
            return current

        async def no_navigation(*args, **kwargs):
            return None

        async def page_text(page):
            return "Checkout: Your Information"

        with mock.patch("visit.open_start_page", no_navigation), mock.patch.object(retest, "_page_text", page_text):
            outcome = asyncio.run(retest._replay(Ctx(), plan or self.plan, Browse, tools, current_url, 20))
        return outcome, tools

    def test_the_same_route_is_followed_and_the_action_is_tried_again(self):
        answers = {**self.route_ok, self.acting: {"success": True, "changed": True, "url": CHECKOUT,
                                                  "field": {"contains_typed_text": True}}}
        outcome, tools = self.replay(answers)
        self.assertTrue(outcome["followed"])
        self.assertEqual(tools.asked[-1], self.acting)
        self.assertTrue(outcome["observed"]["field_ok"])
        self.assertEqual(outcome["evidence_step"], 5, "four route steps and then the action")

    def test_a_step_that_leads_somewhere_else_stops_the_replay_and_nothing_is_retried(self):
        answers = {**self.route_ok,
                   "click the Checkout button": {"success": True, "changed": True, "url": START + "basket.html"}}
        outcome, tools = self.replay(answers)
        self.assertFalse(outcome["followed"])
        self.assertIn("flow has changed", outcome["why"])
        self.assertIn("basket.html", outcome["why"])
        self.assertNotIn(self.acting, tools.asked, "a different route is never treated as equivalent")

    def test_a_step_with_no_effect_stops_the_replay(self):
        answers = {**self.route_ok, "click the Login button": {"success": False, "changed": False, "url": START}}
        outcome, tools = self.replay(answers)
        self.assertFalse(outcome["followed"])
        self.assertIn("no effect", outcome["why"])
        self.assertEqual(len(tools.asked), 2, "stopped at the failing step")

    def test_a_route_that_ends_on_another_page_is_not_followed_to_the_action(self):
        outcome, tools = self.replay(dict(self.route_ok), current=START + "cart.html")
        self.assertFalse(outcome["followed"])
        self.assertIn("not on the page the problem was on", outcome["why"])
        self.assertNotIn(self.acting, tools.asked)

    def test_a_bot_check_on_the_route_is_not_attempted(self):
        answers = {**self.route_ok, "click the Login button": {"success": False, "changed": False,
                                                               "bot_check": True, "url": START}}
        outcome, _ = self.replay(answers)
        self.assertFalse(outcome["followed"])
        self.assertIn("bot check", outcome["why"])

    def test_refusals_before_any_browser_opens(self):
        ctx = Ctx()
        ctx.record = []
        signs_in = {**self.plan, "route": [{"idx": 2, "tool": "sign_in", "instruction": "", "url": START}]}
        signs_up = {**self.plan, "route": [{"idx": 2, "tool": "sign_up", "instruction": "", "url": START}]}
        back = {**self.plan, "route_error": "the original route used Back, which is not replayed"}
        no_action = {**self.plan, "acting_tool": None, "acting_instruction": None}
        out = asyncio.run(retest.guided_pass(ctx, [signs_in, signs_up, back], [0, 1, 2]))
        self.assertIn("test account", out[0]["why"])
        self.assertIn("signed up", out[1]["why"])
        self.assertIn("Back", out[2]["why"])
        out = asyncio.run(retest.guided_pass(ctx, [no_action], [0]))
        self.assertIn("no recorded action", out[0]["why"])
        self.assertTrue(all(not o["followed"] for o in out.values()))

    def test_at_most_three_findings_are_followed(self):
        ctx = Ctx()
        ctx.record = []
        back = {**self.plan, "route_error": "the original route used Back, which is not replayed"}
        out = asyncio.run(retest.guided_pass(ctx, [back] * 5, [0, 1, 2, 3, 4]))
        self.assertEqual([out[i]["why"].startswith("the original route used Back") for i in range(3)],
                         [True, True, True])
        self.assertIn("limit", out[3]["why"])
        self.assertIn("limit", out[4]["why"])


# ----------------------------------------------------------------------------------- what a retest may take

class NoLoginIsCopied(unittest.IsolatedAsyncioTestCase):
    async def test_the_original_is_read_without_its_secrets(self):
        import db

        tables = []

        class Query:
            def __init__(self, table):
                self.table, self.columns = table, ""

            def select(self, columns):
                self.columns = columns
                tables.append((self.table, columns))
                return self

            def eq(self, *args):
                return self

            def order(self, *args):
                return self

            async def execute(self):
                if self.table == "runs":
                    return type("R", (), {"data": [{"id": "orig", "url": START, "start_url": None,
                                                    "findings": [], "verdict": None}]})()
                return type("R", (), {"data": []})()

        class Client:
            def table(self, name):
                return Query(name)

        async def fake_client():
            return Client()

        with mock.patch.object(db, "client", fake_client):
            info = await db.get_original_for_retest("orig")
        self.assertEqual({t for t, _ in tables}, {"runs", "steps"}, "run_secrets is never read")
        self.assertNotIn("password", " ".join(c for _, c in tables).lower())
        self.assertEqual(set(info), {"run_id", "findings", "verdict", "start_url", "steps"})

    async def test_a_retest_gets_only_the_login_given_for_it(self):
        import worker_run

        taken, seen = [], {}

        class FakeDb:
            async def take_run_secrets(self, run_id):
                taken.append(run_id)
                return None  # nothing was given for this check

            async def delete_run_secrets(self, run_id):
                pass

            async def finish_run(self, *args, **kwargs):
                pass

            async def fail_run(self, *args, **kwargs):
                pass

            async def get_original_for_retest(self, run_id):
                return {"run_id": run_id, "findings": [old_finding()], "verdict": None, "start_url": START,
                        "steps": ORIGINAL_STEPS}

            class RunRecorder:
                def __init__(self, run_id):
                    pass

        async def first_visit(url, goal, run_id, recorder=None, **kwargs):
            seen.update(kwargs)
            return {"outcome": "achieved", "steps": 1, "reason": "ok", "run_facts": {}}

        fake = FakeDb()
        with mock.patch.multiple(worker_run.db, take_run_secrets=fake.take_run_secrets,
                                 delete_run_secrets=fake.delete_run_secrets, finish_run=fake.finish_run,
                                 fail_run=fake.fail_run, RunRecorder=fake.RunRecorder,
                                 get_original_for_retest=fake.get_original_for_retest), \
                mock.patch.object(worker_run, "first_visit", first_visit):
            # The original used a test login; the retest was queued without one.
            await worker_run.execute({"id": "retest-1", "url": START, "goal": "g", "retest_of": "orig",
                                      "has_test_login": False, "access_mode": "account"}, "v")
        self.assertEqual(taken, [], "no secrets were asked for: this run has none, and the original's are gone")
        self.assertIsNone(seen["credentials"])
        info = seen["retest"]
        self.assertEqual(info["run_id"], "orig")
        flat = repr(info).lower()
        for word in ("password", "test_email", "secret"):
            self.assertNotIn(word, flat)

    def test_the_visitor_is_never_told_the_old_findings(self):
        import inspect

        import dataclasses

        import browse
        import tools

        self.assertNotIn("retest", inspect.getsource(browse).lower(),
                         "the independent visit's code knows nothing of a retest")
        self.assertNotIn("retest", {f.name for f in dataclasses.fields(tools.RunContext)})


if __name__ == "__main__":
    unittest.main()


class LooserMatchAndFallbackVerdict(unittest.TestCase):
    def test_the_same_problem_worded_differently_on_the_same_page_is_the_old_finding(self):
        # From the real saucedemo retest: the same Last Name problem, written up two different ways.
        old = old_finding(title="Checkout First Name field shows 'User' and Last Name stays empty",
                          happened="First Name ended up showing 'User' and Last Name stayed empty.")
        new = {"title": "Last Name field does not accept typed text on checkout step one", "kind": "site_problem",
               "happened": "Typing 'Doe' into Last Name left it empty and replaced the first name.",
               "evidence": {"step": 10, "url": CHECKOUT}}
        self.assertTrue(retest.same_problem(old, new))
        elsewhere = {**new, "evidence": {"step": 4, "url": START + "inventory.html"}}
        self.assertFalse(retest.same_problem(old, elsewhere), "another page is another problem")
        other = {"title": "Continue button gives no error for an empty postal code", "kind": "site_problem",
                 "happened": "Nothing is shown when the postal code is missing.",
                 "evidence": {"step": 12, "url": CHECKOUT}}
        self.assertFalse(retest.same_problem(old, other), "a different problem on the same page")

    def test_an_original_without_a_verdict_gets_one_from_its_row(self):
        row = {"outcome": "blocked", "reason": "Last Name stayed empty.", "entry": {"blocked_at_login": False},
               "result": {"stopped_by": "finish", "verification": None, "agent_issues": [],
                          "frictions": [{"kind": "site", "step": 13, "url": CHECKOUT,
                                         "happened": "First Name ended up showing 'User'", "detected_by": "model"}]}}
        v = retest.fallback_verdict(row)
        self.assertEqual(v["kind"], "stuck")
        self.assertIn("checkout-step-one", v["headline"])
        self.assertEqual(v["where_step"], 13)
        self.assertEqual(retest.compare_verdicts(v, {"kind": "got_through", "headline": "h"})["change"], "improved")


class DuplicatesAndLegacyLogins(unittest.TestCase):
    def test_a_problem_written_up_twice_by_the_retest_is_the_old_one_not_a_new_one(self):
        findings = [old_finding()]
        plans = build_plans(findings, ORIGINAL_STEPS, START)
        twice = [
            {"title": "Last Name field rejects typed text", "kind": "site_problem",
             "happened": "Typing into Last Name left it empty.", "evidence": {"step": 18, "url": CHECKOUT}},
            {"title": "First Name field received the Last Name value", "kind": "site_problem",
             "happened": "The Last Name text appeared in the First Name field.",
             "evidence": {"step": 12, "url": CHECKOUT}},
        ]
        out = labels(plans, findings, record=[], new=twice)
        self.assertEqual(out["labels"][0]["label"], "still_present")
        self.assertEqual(out["labels"][0]["evidence_step"], 12, "the earliest of them")
        self.assertEqual(out["new"], [], "neither is new")

    def test_a_legacy_login_block_that_got_past_the_login_is_not_a_login_wall(self):
        row = {"outcome": "blocked", "reason": "I logged in with the password shown on the page, then checkout failed.",
               "entry": {"blocked_at_login": True, "page_login": "shown_on_page"},
               "result": {"stopped_by": "finish", "verification": None, "agent_issues": [], "frictions": []}}
        steps = [step(1, "look", url=START), step(4, "do", "click Login", url=START + "inventory.html")]
        self.assertEqual(retest.fallback_verdict(row, steps)["kind"], "stuck")
        stuck_at_login = [step(1, "look", url=START), step(3, "do", "click Login", url=START)]
        self.assertEqual(retest.fallback_verdict(row, stuck_at_login)["kind"], "login_wall")
