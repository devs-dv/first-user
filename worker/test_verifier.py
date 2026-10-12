"""Tests for the verifier's verdict handling, with the model mocked (no network).

Usage: python -m unittest test_verifier -v
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)
import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.pop("NEATLOGS_API_KEY", None)  # nothing here should be exported

import verifier  # noqa: E402


class FakePage:
    async def evaluate(self, js):
        return "[]" if "querySelectorAll" in js else "Hello World!"

    async def url(self):
        return "https://example.com/"

    async def title(self):
        return "Example"

    async def screenshot(self, **kwargs):
        return b"\x89PNG\r\n\x1a\n"


def fake_client(tool_input: dict):
    block = SimpleNamespace(type="tool_use", input=tool_input)
    response = SimpleNamespace(
        content=[block], model="claude-haiku-5-5",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )

    class Messages:
        calls: list[dict] = []

        async def create(self, **kwargs):
            Messages.calls.append(kwargs)
            return response

    class Client:
        messages = Messages()

        async def close(self):
            pass

    return Client(), Messages


def run_verify(tool_input: dict, record=None):
    client, messages = fake_client(tool_input)
    with mock.patch.object(verifier.neatlogs, "wrap", lambda c: client), \
            mock.patch.object(verifier, "AsyncAnthropic", lambda: object()):
        result = asyncio.run(verifier.verify.__wrapped__("Do the thing.", record or [], FakePage()))
    return result, messages


class VerdictHandling(unittest.TestCase):
    def test_contradicted_needs_quoted_positive_evidence(self):
        result, _ = run_verify({"verdict": "contradicted", "reason": "Nothing shows the click.",
                                "contradicting_evidence": ""})
        self.assertEqual(result["verdict"], "unverified")
        self.assertEqual(result["downgraded_from"], "contradicted")

    def test_contradicted_with_evidence_stands(self):
        result, _ = run_verify({"verdict": "contradicted", "reason": "Locked out.",
                                "contradicting_evidence": "Epic sadface: Sorry, this user has been locked out."})
        self.assertEqual(result["verdict"], "contradicted")
        self.assertIn("locked out", result["contradicting_evidence"])

    def test_verified_and_unverified_pass_through(self):
        for verdict in ("verified", "unverified"):
            result, _ = run_verify({"verdict": verdict, "reason": "r", "contradicting_evidence": ""})
            self.assertEqual(result["verdict"], verdict)
            self.assertNotIn("downgraded_from", result)

    def test_an_unexpected_verdict_is_unverified(self):
        result, _ = run_verify({"verdict": "failed", "reason": "r", "contradicting_evidence": ""})
        self.assertEqual(result["verdict"], "unverified")


class WhatTheVerifierSees(unittest.TestCase):
    def test_prompt_separates_absent_from_present_evidence(self):
        prompt = verifier.SYSTEM_PROMPT
        self.assertIn("ONLY when there is positive evidence", prompt)
        self.assertIn("never contradicting evidence", prompt)
        self.assertIn("choose unverified", prompt)
        required = verifier.VERDICT_TOOL["input_schema"]["required"]
        self.assertIn("contradicting_evidence", required)

    def test_an_empty_record_is_not_shown_as_evidence_of_failure(self):
        text = verifier.format_record([])
        self.assertIn("says nothing about whether the task was completed", text)
        self.assertNotIn("(no actions)", text)

    def test_the_agents_reasoning_never_reaches_the_verifier(self):
        record = [{"step": 1, "tool": "do", "instruction": "click Login", "page_changed": True,
                   "url_after": "https://example.com/"}]
        _, messages = run_verify({"verdict": "verified", "reason": "r", "contradicting_evidence": ""}, record)
        sent = json.dumps(messages.calls[-1]["messages"])
        self.assertIn("click Login", sent)
        for forbidden in ("thought", "finish", "note_friction", "agent_reason"):
            self.assertNotIn(forbidden, sent)


if __name__ == "__main__":
    unittest.main()
