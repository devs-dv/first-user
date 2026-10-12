"""Tests for the feedback loop's backend and eval side: real-world cases from live runs, the --cases flag
and the feedback report.

Usage: python -m unittest test_feedback_loop -v

Nothing here touches the database or the queue.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)

import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))

import cases  # noqa: E402
import feedback_report  # noqa: E402
import from_run  # noqa: E402

RUN_ID = "8ca3896f-a3d8-475f-b810-5c9b6b98bb9e"


def run_row(**overrides) -> dict:
    row = {"id": RUN_ID, "url": "https://shop.example/", "goal": "Buy a mug.", "access_mode": "public",
           "start_url": None, "success_condition": "An order confirmation appears.", "has_test_login": False,
           "status": "done", "kind": "test"}
    row.update(overrides)
    return row


class CaseFromARun(unittest.TestCase):
    def test_the_fields_a_case_needs_are_copied(self):
        case = cases.case_from_run(run_row(), "achieved", "A person can buy a mug.", date(2026, 10, 12))
        self.assertEqual(case, {
            "id": "real_8ca3896f", "kind": "achievable", "url": "https://shop.example/", "goal": "Buy a mug.",
            "access_mode": "public", "start_url": None, "success_condition": "An order confirmation appears.",
            "expected_outcome": "achieved", "note": "A person can buy a mug.", "source_run_id": RUN_ID,
            "added": "2026-10-12",
        })

    def test_a_broken_case_carries_the_note_as_the_known_issue_for_the_judge(self):
        case = cases.case_from_run(run_row(), "broken", "Checkout shows 'Last name is required' with it filled in.")
        self.assertEqual((case["kind"], case["expected_outcome"]), ("broken", "broken"))
        self.assertEqual(case["known_issue"], case["note"])

    def test_a_test_login_is_never_copied_only_the_fact_that_one_is_needed(self):
        row = run_row(access_mode="account", has_test_login=True, test_email="me@x.example",
                      test_password="hunter2-hunter2", password="x")
        case = cases.case_from_run(row, "achieved", "Signs in and sees the dashboard.")
        blob = json.dumps(case)
        for secret in ("me@x.example", "hunter2", "test_email", "test_password", "password"):
            self.assertNotIn(secret, blob)
        self.assertTrue(case["needs_test_login"])
        self.assertFalse(cases.runnable(case)[0])

    def test_a_start_link_with_a_token_is_not_kept(self):
        case = cases.case_from_run(run_row(access_mode="link", start_url="https://app.example/demo?token=abc123"),
                                   "achieved", "The demo opens on a dashboard.")
        self.assertIsNone(case["start_url"])
        self.assertTrue(case["needs_start_link"])
        self.assertNotIn("abc123", json.dumps(case))
        clean = cases.case_from_run(run_row(access_mode="link", start_url="https://app.example/demo"),
                                    "achieved", "The demo opens on a dashboard.")
        self.assertEqual(clean["start_url"], "https://app.example/demo")
        self.assertTrue(cases.runnable(clean)[0])

    def test_an_address_with_a_password_or_a_goal_with_a_key_is_refused(self):
        with self.assertRaises(cases.NotSafeToCopy):
            cases.case_from_run(run_row(url="https://user:pw@shop.example/"), "achieved", "n")
        with self.assertRaises(cases.NotSafeToCopy):
            # Built at run time, so no key-shaped string sits in this file for the secret scan to find.
            fake_key = "sk" + "-ant-" + "api03-" + "abcdefghijklmnop"
            cases.case_from_run(run_row(goal=f"Log in with key {fake_key}"), "achieved", "n")
        with self.assertRaises(cases.NotSafeToCopy):
            fake_bearer = "Bear" + "er " + "abcdefghijklmnopqrstuvwx"
            cases.case_from_run(run_row(), "achieved", f"Authorization: {fake_bearer}")

    def test_the_expectation_and_a_note_are_required(self):
        with self.assertRaises(ValueError):
            cases.case_from_run(run_row(), "maybe", "n")
        with self.assertRaises(ValueError):
            cases.case_from_run(run_row(), "achieved", "   ")

    def test_adding_the_same_run_twice_replaces_the_case(self):
        first = cases.case_from_run(run_row(), "achieved", "one")
        second = cases.case_from_run(run_row(), "broken", "two")
        other = cases.case_from_run(run_row(id="11111111-aaaa-bbbb-cccc-222222222222"), "achieved", "other")
        document = cases.merge_case(cases.merge_case(cases.merge_case(None, first), other), second)
        self.assertEqual([c["note"] for c in document["cases"]], ["other", "two"])


class TheFile(unittest.TestCase):
    def test_from_run_writes_real_world_json_and_load_cases_reads_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sites.json").write_text(json.dumps({"cases": [
                {"id": "site_a", "kind": "achievable", "url": "https://a.example/", "goal": "g"}]}), encoding="utf-8")
            total = from_run.add_to_file(cases.case_from_run(run_row(), "achieved", "n"), root / "real_world.json")
            self.assertEqual(total, 1)
            self.assertEqual([c["id"] for c in cases.load_cases(None, "sites", root)], ["site_a"])
            self.assertEqual([c["id"] for c in cases.load_cases(None, "real_world", root)], ["real_8ca3896f"])
            self.assertEqual([c["id"] for c in cases.load_cases(None, "all", root)], ["site_a", "real_8ca3896f"])
            self.assertEqual([c["id"] for c in cases.load_cases(["site_a"], "all", root)], ["site_a"])

    def test_without_a_real_world_file_all_is_just_the_sites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sites.json").write_text(json.dumps({"cases": [{"id": "s", "kind": "achievable"}]}),
                                             encoding="utf-8")
            self.assertEqual(cases.load_cases(None, "real_world", root), [])
            self.assertEqual(len(cases.load_cases(None, "all", root)), 1)

    def test_the_committed_real_world_file_if_present_holds_no_secrets(self):
        path = ROOT / "evals" / "real_world.json"
        if not path.exists():
            self.skipTest("no real_world.json yet")
        text = path.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"sk-ant-|eyJ[A-Za-z0-9_-]{8,}\.|test_password|test_email", text))

    def test_run_py_has_the_cases_flag_and_passes_how_to_get_in(self):
        source = (ROOT / "evals" / "run.py").read_text(encoding="utf-8")
        self.assertIn('"--cases"', source)
        self.assertIn('choices=["sites", "real_world", "all"]', source)
        self.assertIn('for key in ("access_mode", "start_url", "success_condition")', source)
        self.assertIn("case_files.runnable", source)


class TheFeedbackReport(unittest.TestCase):
    VOTES = (
        [{"run_id": "r1", "finding_id": f"f{i}", "verdict": "useful"} for i in range(5)]
        + [{"run_id": "r1", "finding_id": "f9", "verdict": "not_a_problem"}]
        + [{"run_id": "r2", "finding_id": "f0", "verdict": "not_a_problem"}]
        + [{"run_id": "r2", "finding_id": "f1", "verdict": "fixed"},
           {"run_id": "r2", "finding_id": "f2", "verdict": "fixed"},
           {"run_id": "r3", "finding_id": "f0", "verdict": "fixed"}]
    )

    def test_counts_and_the_false_positive_rate(self):
        summary = feedback_report.summarise(self.VOTES, None)
        self.assertEqual(summary["counts"], {"useful": 5, "not_a_problem": 2, "fixed": 3})
        self.assertEqual(summary["total"], 10)
        self.assertAlmostEqual(summary["false_positive_rate"], 0.2)

    def test_without_retest_data_the_line_says_not_available_yet(self):
        text = feedback_report.render(feedback_report.summarise(self.VOTES, None))
        self.assertIn("not a real problem", text)
        self.assertIn("20% (2 of 10)", text)
        self.assertIn("a later retest labelled Fixed: not available yet", text)

    def test_with_retest_data_fixed_votes_are_matched_to_the_retest_label(self):
        retests = {("r2", "f1"): "Fixed", ("r2", "f2"): "Not fixed", ("r9", "f0"): "Fixed"}
        summary = feedback_report.summarise(self.VOTES, retests)
        self.assertEqual((summary["fixed_confirmed"], summary["fixed_votes_retested"]), (1, 2))
        self.assertIn("1 of 2 retested (3 voted fixed in all)", feedback_report.render(summary))

    def test_the_retest_labels_are_read_from_the_shape_the_worker_writes(self):
        # runs.retest of a Check again run: labels carry finding_index into the ORIGINAL run's findings.
        originals = {"orig": [{"title": "a"}, {"id": "abc-1", "title": "b"}, {"id": "bad id!", "title": "c"}]}
        rows = [{"retest_of": "orig", "finished_at": "2026-10-12T10:00:00Z", "retest": {
            "original_run_id": "orig",
            "labels": [{"finding_index": 0, "label": "fixed", "pass": "independent"},
                       {"finding_index": 1, "label": "still_present"},
                       {"finding_index": 2, "label": "not_reached"},
                       {"finding_index": 7, "label": "fixed"}],
            "new": [{"title": "n", "label": "new"}]}}]
        labels = feedback_report.retest_labels(rows, originals)
        self.assertEqual(labels, {("orig", "f0"): "fixed", ("orig", "abc-1"): "still_present",
                                  ("orig", "f2"): "not_reached"})
        votes = [{"run_id": "orig", "finding_id": "f0", "verdict": "fixed"},
                 {"run_id": "orig", "finding_id": "abc-1", "verdict": "fixed"},
                 {"run_id": "orig", "finding_id": "f2", "verdict": "fixed"}]
        summary = feedback_report.summarise(votes, labels)
        self.assertEqual((summary["fixed_confirmed"], summary["fixed_votes_retested"]), (1, 3))

    def test_the_latest_retest_of_an_original_wins_and_a_missing_original_is_skipped(self):
        originals = {"orig": [{}]}
        rows = [{"retest_of": "orig", "finished_at": "2026-10-12T12:00:00Z",
                 "retest": {"labels": [{"finding_index": 0, "label": "fixed"}]}},
                {"retest_of": "orig", "finished_at": "2026-10-12T09:00:00Z",
                 "retest": {"labels": [{"finding_index": 0, "label": "still_present"}]}},
                {"retest_of": "gone", "finished_at": "2026-10-12T09:00:00Z",
                 "retest": {"labels": [{"finding_index": 0, "label": "fixed"}]}}]
        self.assertEqual(feedback_report.retest_labels(rows, originals), {("orig", "f0"): "fixed"})

    def test_finding_ids_follow_the_web_rule(self):
        self.assertEqual(feedback_report.finding_ids([{}, {"id": "abc123"}, {"id": "bad id!"}, {"id": 5}]),
                         ["f0", "abc123", "f2", "f3"])
        self.assertEqual(feedback_report.finding_ids(None), [])
        web = (ROOT / "web" / "lib" / "feedback-logic.ts").read_text(encoding="utf-8")
        self.assertIn("const FINDING_ID = /" + feedback_report.FINDING_ID.pattern + "/;", web)
        self.assertIn("`f${index}`", web)

    def test_no_votes_is_not_a_division_by_zero(self):
        summary = feedback_report.summarise([], None)
        self.assertIsNone(summary["false_positive_rate"])
        self.assertIn("n/a, no votes yet", feedback_report.render(summary))


class TheFeedbackSql(unittest.TestCase):
    def setUp(self):
        self.sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")

    def test_the_feedback_block_is_last_and_appears_once(self):
        self.assertEqual(self.sql.count("-- FEEDBACK (2026-10-12)"), 1)
        after = self.sql[self.sql.index("-- FEEDBACK (2026-10-12)"):]
        # No other section heading follows it, and it creates just the one table.
        self.assertEqual(re.findall(r"^-- [-=]{20,}\n-- [A-Za-z]", after, re.M), [])
        self.assertEqual(after.count("create table"), 1)

    def test_one_vote_per_finding_per_visitor_and_no_other_personal_data(self):
        block = self.sql[self.sql.index("-- FEEDBACK (2026-10-12)"):]
        self.assertIn("primary key (run_id, finding_id, ip_hash)", block)
        self.assertIn("check (verdict in ('useful', 'not_a_problem', 'fixed'))", block)
        self.assertIn("on conflict (run_id, finding_id, ip_hash)", block)
        self.assertIn("alter table public.finding_feedback enable row level security", block)
        self.assertNotRegex(block, r"(?i)\b(email|user_agent|ip_address|name)\b\s+text")

    def test_the_one_live_enqueue_web_run_is_the_eleven_argument_one_with_retest_of_last(self):
        final = self.sql.rindex("create or replace function public.enqueue_web_run(")
        definition = self.sql[final:final + 900]
        self.assertIn("p_success_condition text default null,\n  p_retest_of uuid default null\n)", definition)
        # Nothing after the final definition redefines or drops it, and each earlier one was dropped by
        # the block that replaced it.
        self.assertEqual(self.sql.count("create or replace function public.enqueue_web_run(", final + 1), 0)
        self.assertEqual(self.sql.count("drop function if exists public.enqueue_web_run(", final + 1), 0)
        self.assertEqual(self.sql.count("create or replace function public.enqueue_web_run("),
                         self.sql.count("drop function if exists public.enqueue_web_run("))

    def test_the_blocks_are_in_order_and_each_appears_once(self):
        heads = ["REPORT V2 (2026-10-12)", "Understand mode (2026-10-12)", "Founder brief (2026-10-12)",
                 "CHECK AGAIN (2026-10-12)", "FEEDBACK (2026-10-12)"]
        positions = [self.sql.index("-- " + h) for h in heads]
        self.assertEqual(positions, sorted(positions))
        for h in heads:
            self.assertEqual(self.sql.count("-- " + h), 1)
        self.assertNotRegex(self.sql, r"(?m)^(<<<<<<<|=======|>>>>>>>)")


class TheVoteRoute(unittest.TestCase):
    def test_the_route_checks_the_run_and_finding_and_hashes_the_ip_like_the_other_routes(self):
        source = (ROOT / "web" / "app" / "api" / "runs" / "[id]" / "feedback" / "route.ts").read_text(encoding="utf-8")
        self.assertIn('import { clientIp, hashIp } from "@/lib/visitor";', source)
        self.assertIn("hashIp(clientIp(request.headers))", source)
        self.assertIn("findingIds(", source)
        self.assertIn('"finding_not_found"', source)
        self.assertIn('rpc("record_finding_feedback"', source)
        self.assertNotIn("neatlogs", source)


if __name__ == "__main__":
    unittest.main()
