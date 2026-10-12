"""Tests for the founder brief.

Usage: python -m unittest test_founder_brief -v

No model is called and nothing is fetched: the model is a stand-in that returns whatever a test wants
(including things it must not be believed about), and the brief it works from is a stored product brief.
"""

import json
import re
import unittest
from unittest import mock

import founder_brief as fb

HOME = "https://acme.example/"
ABOUT = "https://acme.example/about"
PRICING = "https://acme.example/pricing"


def stored_brief() -> dict:
    return {
        "version": 1, "url": HOME, "one_liner": "Acme tracks invoices for small shops.",
        "what_it_does": "Matches invoices to bank payments.", "who_its_for": "Small shops.",
        "how_it_works": "Connect your bank.", "primary_value": "Never chase a late invoice.",
        "pricing": {"status": "published", "note": "", "source_urls": [PRICING],
                    "tiers": [{"name": "Starter", "price": "$9 /month", "what_you_get": "One shop",
                               "source_url": PRICING}]},
        "business_model": {"label": "inferred", "model": "Subscription after a free trial",
                           "evidence": [{"quote": "Start your free trial today.", "source_url": HOME}]},
        "claims": [
            {"claim": "More than 2,000 shops use Acme", "source_url": ABOUT, "status": "confirmed",
             "quote": "More than 2,000 shops use Acme every week."},
            {"claim": "Works with any bank", "source_url": HOME, "status": "inferred", "quote": ""},
            {"claim": "Replaces spreadsheets and QuickBooks", "source_url": HOME, "status": "confirmed",
             "quote": "Replace your spreadsheets and QuickBooks."},
            {"claim": "Might do payroll", "source_url": HOME, "status": "unknown", "quote": ""},
        ],
        "unknowns": ["Who funds the company."],
        "suggested_journeys": [{"goal": "Start a free trial", "success": "A welcome page",
                                "source_url": HOME, "basis": "call_to_action",
                                "basis_text": "Start your free trial today", "claim_to_test": False}],
        "pages": [
            {"url": HOME, "kind": "home", "title": "Acme", "method": "http", "status": 200, "bytes": 10},
            {"url": ABOUT, "kind": "about", "title": "About", "method": "http", "status": 200, "bytes": 10},
            {"url": PRICING, "kind": "pricing", "title": "Pricing", "method": "http", "status": 200, "bytes": 10},
        ],
        "skipped": [], "limits": {"seconds": 1, "browser_reads": 0, "stopped": None},
    }


def stmt(text: str, *refs: str) -> dict:
    return {"text": text, "refs": list(refs)}


def good_raw() -> dict:
    return {
        "executive_summary": {
            "building": stmt("Acme builds invoice tracking for small shops.", "c1", "p1"),
            "for_whom": stmt("Small shops.", "c1"),
            "problem": stmt("Late invoices are hard to chase.", "j1"),
            "solution": stmt("It matches invoices to bank payments.", "c3"),
            "business_model": stmt("Subscription after a free trial, as we read it.", "e1", "t1"),
        },
        "opportunity": {
            "problem": stmt("Shops track invoices in spreadsheets.", "c3"),
            "alternatives": [{"name": "QuickBooks", "refs": ["c3"]}, {"name": "Xero", "refs": ["c3"]}],
            "target_users": stmt("Owners of small shops.", "c1"),
            "why_different": stmt("It targets very small shops rather than accountants.", "c1"),
        },
        "product": {
            "core_features": [stmt("Bank matching.", "c3"), stmt("Invented feature.", "c99")],
            "maturity_signals": [stmt("A public pricing page with one plan.", "t1")],
        },
        "traction_refs": ["c1", "c2", "c3", "c4", "p1", "c99"],
        "missing_evidence": ["No revenue figures are shown.", "No named customers."],
        "risks": {
            "technical": [stmt("Bank connections depend on third-party access.", "c2")],
            "competitive": [stmt("Established accounting tools already do this.", "c3")],
            "go_to_market": [stmt("The site gives no sign of how shops will find it.")],
        },
        "readiness": [
            {"dimension": key, "shows": [stmt(f"Public evidence for {key}.", "c1")], "unknown": ["Not stated."],
             "question": "What would you show someone to prove this?"}
            for key in fb.DIMENSION_KEYS
        ],
    }


def all_strings(value, skip=("quote",), path=()):
    """Every string in the output with its key path, except values under the skipped keys."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in skip:
                continue
            yield from all_strings(item, skip, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from all_strings(item, skip, path + (index,))
    elif isinstance(value, str):
        yield path, value


def all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_keys(item)


class NoScoreAnywhere(unittest.TestCase):
    def test_a_clean_report_has_no_score_rating_or_percentage_and_is_not_empty(self):
        out = fb.build_founder_brief(good_raw(), stored_brief(), "b1")
        self.assertIn("Acme builds invoice tracking", out["executive_summary"]["building"]["text"])
        # Everything we wrote, and everything in it that is not the company's own quoted words or price list.
        company_text = {"pricing", "business_model"}
        for path, text in all_strings(out):
            if len(path) > 1 and path[1] in company_text:
                continue
            self.assertFalse(fb.has_forbidden(text), (path, text))
        for key in all_keys(out):
            self.assertNotRegex(str(key), r"(?i)score|rating|percent|probab|grade")

    def test_text_that_rates_scores_or_names_an_investor_is_dropped_wherever_it_appears(self):
        bad = [
            "Product differentiation is strong at 85%.", "We rate the demand 7/10.", "Overall score: good.",
            "A high risk company.", "Likelihood of acceptance is moderate.", "Y Combinator would like this.",
            "Sequoia and a16z back companies like this.", "Traction level: low", "Chances of funding are good.",
            "Great potential here.", "Would suit an accelerator.",
        ]
        raw = good_raw()
        raw["executive_summary"]["building"] = stmt(bad[0], "c1")
        raw["opportunity"]["why_different"] = stmt(bad[1], "c1")
        raw["product"]["core_features"] = [stmt(t, "c3") for t in bad[2:6]]
        raw["risks"]["technical"] = [stmt(t, "c2") for t in bad[6:]]
        raw["missing_evidence"] = bad[:3]
        raw["readiness"][0]["shows"] = [stmt(t, "c1") for t in bad]
        raw["readiness"][0]["unknown"] = bad
        raw["readiness"][0]["question"] = "How strong is your demand, out of 10?"
        out = fb.build_founder_brief(raw, stored_brief())
        self.assertEqual(out["executive_summary"]["building"]["status"], "unknown")
        self.assertEqual(out["opportunity"]["why_different"]["status"], "unknown")
        self.assertEqual(out["product_and_business_model"]["core_features"], [])
        self.assertEqual(out["evidence_and_risks"]["risks"]["technical"], [])
        first = out["readiness"][0]
        self.assertEqual((first["shows"], first["unknown"]), ([], []))
        self.assertEqual(first["question"], fb.DIMENSIONS[0][2])
        blob = json.dumps(out)
        for needle in ("85%", "7/10", "Combinator", "Sequoia", "a16z", "acceptance", "accelerator"):
            self.assertNotIn(needle, blob)

    def test_ratings_in_the_models_words_for_readiness_never_become_a_number_or_level(self):
        raw = good_raw()
        for entry in raw["readiness"]:
            entry["shows"] = [stmt("Rated high for clarity.", "c1"), stmt("The About page names the audience.", "c1")]
        out = fb.build_founder_brief(raw, stored_brief())
        for dim in out["readiness"]:
            self.assertEqual([s["text"] for s in dim["shows"]], ["The About page names the audience."])
            self.assertEqual(set(dim), {"dimension", "label", "shows", "unknown", "question"})


class StatedTractionIsAlwaysUnverified(unittest.TestCase):
    def test_only_confirmed_claims_with_a_quote_become_traction_and_each_is_labelled(self):
        out = fb.build_founder_brief(good_raw(), stored_brief())
        traction = out["evidence_and_risks"]["traction"]
        self.assertEqual([t["claim"] for t in traction],
                         ["More than 2,000 shops use Acme", "Replaces spreadsheets and QuickBooks"])
        for item in traction:
            self.assertEqual(item["label"], "Stated by the company, not verified")
            self.assertTrue(item["quote"])
            self.assertIn(item["source_url"], out["pages_read"])
        self.assertEqual(traction[0]["quote"], "More than 2,000 shops use Acme every week.")
        self.assertEqual(out["evidence_and_risks"]["traction_label"], "Stated by the company, not verified")

    def test_the_quote_is_the_stored_one_not_the_models_words(self):
        raw = good_raw()
        raw["traction_refs"] = ["c1"]
        raw["executive_summary"]["building"] = stmt("Acme has 10,000 shops.", "c1")
        out = fb.build_founder_brief(raw, stored_brief())
        self.assertEqual(out["evidence_and_risks"]["traction"][0]["quote"], "More than 2,000 shops use Acme every week.")
        self.assertNotIn("10,000 shops", json.dumps(out["evidence_and_risks"]["traction"]))

    def test_no_traction_is_said_plainly(self):
        raw = good_raw()
        raw["traction_refs"] = []
        raw["missing_evidence"] = []
        out = fb.build_founder_brief(raw, stored_brief())
        self.assertEqual(out["evidence_and_risks"]["traction"], [])
        self.assertTrue(any("No customer numbers" in m for m in out["evidence_and_risks"]["missing_evidence"]))


class EverythingHasASource(unittest.TestCase):
    def collect(self, value):
        if isinstance(value, dict):
            if "sources" in value or "source_url" in value:
                yield value
            for item in value.values():
                yield from self.collect(item)
        elif isinstance(value, list):
            for item in value:
                yield from self.collect(item)

    def test_every_statement_and_traction_item_cites_a_page_that_was_read(self):
        out = fb.build_founder_brief(good_raw(), stored_brief())
        read = set(out["pages_read"])
        found = 0
        for item in self.collect(out):
            urls = [s["url"] for s in item.get("sources", [])] + ([item["source_url"]] if "source_url" in item else [])
            if item.get("status") == "unknown":
                continue
            found += 1
            self.assertTrue(urls, item)
            self.assertTrue(set(urls) <= read, item)
        self.assertGreater(found, 10)

    def test_made_up_references_give_unknown_not_a_statement(self):
        raw = good_raw()
        raw["executive_summary"]["problem"] = stmt("Late invoices.", "c99", "x1", "https://made.up/")
        raw["executive_summary"]["solution"] = stmt("No refs at all.")
        raw["opportunity"]["target_users"] = {"text": "Shops.", "refs": "c1"}
        out = fb.build_founder_brief(raw, stored_brief())
        for key in ("problem", "solution"):
            self.assertEqual(out["executive_summary"][key], {"text": "unknown", "sources": [], "status": "unknown"})
        self.assertEqual(out["opportunity"]["target_users"]["status"], "unknown")
        self.assertNotIn("made.up", json.dumps(out))

    def test_a_claim_whose_source_is_not_a_page_read_is_not_evidence(self):
        brief = stored_brief()
        brief["claims"][1]["source_url"] = "https://elsewhere.example/x"
        raw = good_raw()
        raw["executive_summary"]["for_whom"] = stmt("Anyone.", "c2")
        out = fb.build_founder_brief(raw, brief)
        self.assertEqual(out["executive_summary"]["for_whom"]["status"], "unknown")

    def test_alternatives_are_only_those_the_cited_evidence_names(self):
        out = fb.build_founder_brief(good_raw(), stored_brief())
        self.assertEqual([a["name"] for a in out["opportunity"]["alternatives"]], ["QuickBooks"])
        self.assertTrue(out["opportunity"]["alternatives"][0]["sources"])

    def test_our_assessments_are_labelled_and_still_cite_the_pages_read(self):
        out = fb.build_founder_brief(good_raw(), stored_brief())
        self.assertEqual(out["opportunity"]["why_different"]["label"], "Our assessment")
        for kind, items in out["evidence_and_risks"]["risks"].items():
            self.assertTrue(items, kind)
            for item in items:
                self.assertEqual(item["label"], "Our assessment")
                self.assertTrue(item["sources"])
        self.assertEqual(out["evidence_and_risks"]["risks_label"], "Our assessment")

    def test_prices_and_the_business_model_are_copied_from_the_brief_and_labelled_inferred(self):
        raw = good_raw()
        raw["pricing"] = {"status": "published", "tiers": [{"name": "Gold", "price": "$1"}]}
        out = fb.build_founder_brief(raw, stored_brief())
        pricing = out["product_and_business_model"]["pricing"]
        self.assertEqual(pricing["tiers"], stored_brief()["pricing"]["tiers"])
        self.assertEqual(out["product_and_business_model"]["business_model"]["label"], "inferred")
        brief = stored_brief()
        brief["pricing"] = {"status": "not_published", "tiers": [], "note": "No pricing page.", "source_urls": []}
        self.assertEqual(fb.build_founder_brief(good_raw(), brief)["product_and_business_model"]["pricing"]["status"],
                         "not_published")


class TheFixedNote(unittest.TestCase):
    NOTE = "Built only from the public website. It cannot judge the team, real demand, revenue or retention."

    def test_the_note_is_always_present_and_exact(self):
        self.assertEqual(fb.FOUNDER_NOTE, self.NOTE)
        for raw in (good_raw(), {}, None, [], "junk", {"note": "No note needed.", "executive_summary": 5}):
            out = fb.build_founder_brief(raw, stored_brief())  # type: ignore[arg-type]
            self.assertEqual(out["note"], self.NOTE)
            self.assertEqual(list(out)[2], "note", "the note comes first in the report")

    def test_a_useless_reply_still_gives_all_sections_of_unknowns_and_six_dimensions(self):
        out = fb.build_founder_brief({}, stored_brief())
        self.assertEqual([d["dimension"] for d in out["readiness"]], fb.DIMENSION_KEYS)
        self.assertEqual(len(out["readiness"]), 6)
        self.assertTrue(all(d["question"].endswith("?") for d in out["readiness"]))
        self.assertEqual(out["executive_summary"]["building"]["status"], "unknown")


class NothingIsFetched(unittest.IsolatedAsyncioTestCase):
    async def test_writing_it_uses_no_network_and_sends_only_stored_evidence_to_the_model(self):
        import httpx

        prompts = []

        async def model(prompt):
            prompts.append(prompt)
            return good_raw()

        boom = mock.Mock(side_effect=AssertionError("the founder brief must not fetch anything"))
        with mock.patch.object(httpx.AsyncClient, "stream", boom), mock.patch.object(httpx.AsyncClient, "send", boom), \
                mock.patch("egress.EgressGuard.start", boom), mock.patch("site_reader.SiteReader.get", boom):
            out = await fb.founder_brief(stored_brief(), "b1", fb.TokenTally(), model)
        boom.assert_not_called()
        self.assertEqual(out["source_brief_id"], "b1")
        self.assertIn("[c1] claim [confirmed]", prompts[0])
        self.assertIn("More than 2,000 shops use Acme every week.", prompts[0])

    async def test_a_brief_with_no_pages_is_refused(self):
        with self.assertRaises(ValueError):
            await fb.founder_brief({"claims": [], "pages": []}, "b", fb.TokenTally(), mock.AsyncMock())

    async def test_the_report_is_asked_for_in_parts_and_a_short_part_is_asked_for_again(self):
        asked = []
        full = good_raw()

        async def fake(prompt, usage, keys=None):
            asked.append(list(keys))
            if len(asked) == 1:
                return {"executive_summary": full["executive_summary"]}  # stopped early
            return {key: full[key] for key in keys}

        with mock.patch.object(fb, "_one_reply", fake):
            raw = await fb._ask_model("p", fb.TokenTally())
        self.assertEqual(asked[0], asked[1], "the short part is asked for again")
        self.assertEqual([k for k in asked[2:]], [["traction_refs", "missing_evidence", "risks"], ["readiness"]])
        self.assertEqual(fb.missing_sections(raw), [])

    async def test_it_gives_up_after_three_tries_and_the_run_fails(self):
        calls = []

        async def always_short(prompt, usage, keys=None):
            calls.append(keys)
            return {}

        with mock.patch.object(fb, "_one_reply", always_short):
            with self.assertRaises(fb.FounderBriefIncomplete):
                await fb._ask_model("p", fb.TokenTally())
        self.assertEqual(len(calls), 3)


class RunLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import founder_brief_run

        self.module = founder_brief_run
        self.updates: list[dict] = []

    async def _update(self, run_id, update):
        self.updates.append({"id": run_id, **update})

    async def test_it_is_written_from_the_stored_brief_and_saved_on_the_run(self):
        async def load(source_id):
            self.assertEqual(source_id, "b1")
            return stored_brief()

        async def write(brief, source_id, usage):
            return fb.build_founder_brief(good_raw(), brief, source_id)

        await self.module.execute_founder_brief(
            {"id": "f1", "brief_run_id": "b1"}, "v", load=load, write=write, update=self._update)
        (saved,) = self.updates
        self.assertEqual(saved["status"], "done")
        self.assertEqual(saved["brief"]["note"], fb.FOUNDER_NOTE)

    async def test_without_a_finished_product_brief_the_run_fails_with_a_message(self):
        async def load(source_id):
            return None

        await self.module.execute_founder_brief(
            {"id": "f2", "brief_run_id": "b1"}, "v", load=load, write=mock.AsyncMock(), update=self._update)
        (saved,) = self.updates
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["brief"]["status"], "could_not_write")

    async def test_a_model_failure_fails_the_run_without_leaking_the_error_to_the_page(self):
        async def load(source_id):
            return stored_brief()

        async def write(brief, source_id, usage):
            raise RuntimeError("boom with detail")

        await self.module.execute_founder_brief(
            {"id": "f3", "brief_run_id": "b1"}, "v", load=load, write=write, update=self._update)
        (saved,) = self.updates
        self.assertEqual(saved["status"], "failed")
        self.assertNotIn("boom", saved["brief"]["message"])

    async def test_the_worker_hands_founder_brief_runs_to_this_path(self):
        import worker_run

        with mock.patch("founder_brief_run.execute_founder_brief", new=mock.AsyncMock()) as handler:
            await worker_run.execute({"id": "f4", "kind": "founder_brief", "brief_run_id": "b1"}, "v")
        handler.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
