"""The egress guard's per-host check spans carry their decision (neatlogs incident: "Egress host check requests
finish with empty replies").

Usage: python -m unittest test_egress_spans -v

Two layers: the guard is driven in this process with the span functions replaced by recorders (names are
resolved with a patched resolver, no network), and a child process runs the real neatlogs pipeline with a mask
that keeps every exported span, so the span kind, name, status and output are the ones that would be sent.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)

import asyncio
import contextvars
import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import egress

HERE = Path(__file__).parent
TOKEN = "SECRET-token-0f3a9c"
ADDRESSES = {
    "shop.example": "93.184.216.34",
    "internal.example": "10.0.0.5",
    "localhost.example": "127.0.0.1",
    "linklocal.example": "169.254.10.10",
    "metadata.example": "169.254.169.254",
}
EXPECTED = {
    "shop.example": ("allowed", "public address"),
    "internal.example": ("refused", "private address"),
    "localhost.example": ("refused", "loopback"),
    "linklocal.example": ("refused", "link-local"),
    "metadata.example": ("refused", "metadata address"),
    "gone.example": ("unresolved", "dns failed"),
}


def fake_getaddrinfo(host, port, *args, **kwargs):
    if host not in ADDRESSES:
        raise socket.gaierror("Name or service not known")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ADDRESSES[host], port))]


class RecordsEveryDecision(unittest.IsolatedAsyncioTestCase):
    async def drive(self, hosts: list[str]):
        checks, refusals = [], []
        guard = egress.EgressGuard()
        guard._traced, guard._context = True, contextvars.copy_context()
        with mock.patch("socket.getaddrinfo", fake_getaddrinfo), \
                mock.patch.object(egress, "_check_span", lambda record: checks.append(record) or record), \
                mock.patch.object(egress, "_refusal_span", lambda record: refusals.append(record) or record):
            for host in hosts:
                await guard._vet(host, 443, f"https://{host}/account?token={TOKEN}&id=7#section")
        return checks, refusals

    async def test_every_check_has_a_decision_and_a_short_reason_code(self):
        checks, _ = await self.drive(list(EXPECTED))
        self.assertEqual([c["host"] for c in checks], list(EXPECTED))
        for check in checks:
            with self.subTest(host=check["host"]):
                self.assertEqual(set(check), {"host", "port", "decision", "reason"})
                self.assertEqual((check["decision"], check["reason"]), EXPECTED[check["host"]])
                self.assertEqual(check["port"], 443)
                self.assertIn(check["decision"], ("allowed", "refused", "unresolved"))
                self.assertTrue(check["reason"])

    async def test_a_host_is_checked_once_per_run_however_many_requests_it_gets(self):
        checks, refusals = await self.drive(["shop.example"] * 5 + ["internal.example"] * 3)
        self.assertEqual([c["host"] for c in checks], ["shop.example", "internal.example"])
        self.assertEqual(len(refusals), 3, "each refused request still gets its own refusal record")

    async def test_nothing_secret_or_full_url_is_in_a_check_or_a_refusal_span(self):
        checks, refusals = await self.drive(list(EXPECTED))
        blob = json.dumps([checks, refusals])
        for needle in (TOKEN, "token=", "?", "#section", "id=7"):
            self.assertNotIn(needle, blob)
        for refusal in refusals:
            self.assertEqual(refusal["url"], f"https://{refusal['host']}/account")  # path only

    async def test_a_refusal_is_a_decision_not_an_error(self):
        guard = egress.EgressGuard()
        with mock.patch("socket.getaddrinfo", fake_getaddrinfo):
            decision = await guard._vet("metadata.example", 443, "https://metadata.example/")
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.private)
        record = egress.check_record("metadata.example", 443, decision)
        self.assertEqual(record["decision"], "refused")

    async def test_no_run_active_means_no_spans(self):
        guard = egress.EgressGuard()  # never started: _traced is False, as in tests and scripts
        called = []
        with mock.patch("socket.getaddrinfo", fake_getaddrinfo), \
                mock.patch.object(egress, "_check_span", lambda record: called.append(record)):
            await guard._vet("shop.example", 443, "https://shop.example/")
        self.assertEqual(called, [])

    def test_the_span_is_a_guardrail_named_egress_check(self):
        source = (HERE / "egress.py").read_text(encoding="utf-8")
        self.assertIn('@neatlogs.span(kind="GUARDRAIL", name="egress_check")', source)
        self.assertIn('@neatlogs.span(kind="GUARDRAIL", name="egress_refused")', source)


CHILD = r'''
import test_support, json, socket, asyncio, time
from unittest import mock
import neatlogs

SEEN = []
def mask(span):
    SEEN.append(span)
    return span

neatlogs.init(api_key="a-real-looking-key", endpoint="https://ingest.neatlogs.com", workflow_name="egress-span-test",
              register_shutdown_handlers=False, mask=mask)
import egress
ADDRESSES = %(addresses)s

def fake(host, port, *a, **k):
    if host not in ADDRESSES:
        raise socket.gaierror("Name or service not known")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ADDRESSES[host], port))]

@neatlogs.span(kind="WORKFLOW", name="visit_root")
async def run():
    guard = egress.EgressGuard()
    await guard.start()
    with mock.patch("socket.getaddrinfo", fake):
        for host in %(hosts)s:
            await guard._vet(host, 443, "https://" + host + "/account?token=%(token)s#frag")
    await guard.close()

asyncio.run(run())
neatlogs.flush()
time.sleep(1)
neatlogs.shutdown()
print("SPANS_BEGIN" + json.dumps(SEEN, default=str) + "SPANS_END")
'''


class TheExportedSpans(unittest.TestCase):
    """What neatlogs would actually receive: kind, name, status and output of each check."""

    @classmethod
    def setUpClass(cls):
        child = CHILD % {"addresses": repr(ADDRESSES), "hosts": repr(list(EXPECTED) + ["shop.example"]),
                         "token": TOKEN}
        process = subprocess.run([sys.executable, "-X", "utf8", "-c", child], cwd=HERE, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=180, env=dict(os.environ))
        if process.returncode != 0:
            raise AssertionError(f"the child failed:\n{process.stderr[-1500:]}")
        text = process.stdout
        cls.spans = json.loads(text[text.index("SPANS_BEGIN") + 11:text.index("SPANS_END")])
        cls.checks = [s for s in cls.spans if s["name"] == "egress_check"]
        cls.exported = process.stdout + process.stderr

    def test_one_egress_check_span_per_host_each_with_a_non_empty_output_and_a_decision(self):
        self.assertEqual(len(self.checks), len(EXPECTED), "once per host, not once per request")
        for span in self.checks:
            output = json.loads(span["attributes"]["output.value"])
            with self.subTest(host=output.get("host")):
                self.assertTrue(output)
                self.assertEqual((output["decision"], output["reason"]), EXPECTED[output["host"]])
                self.assertEqual(span["attributes"]["neatlogs.guardrail.output"], span["attributes"]["output.value"])

    def test_they_are_guardrail_spans_not_agent_spans(self):
        for span in self.checks:
            self.assertEqual(span["attributes"]["openinference.span.kind"], "GUARDRAIL")
            self.assertEqual(span["attributes"]["neatlogs.span.kind"], "guardrail")

    def test_a_refusal_is_ok_not_an_error(self):
        refused = [s for s in self.checks if json.loads(s["attributes"]["output.value"])["decision"] == "refused"]
        self.assertEqual(len(refused), 4)
        for span in self.spans:
            if span["name"] in ("egress_check", "egress_refused"):
                self.assertEqual(span["status"]["code"], "OK", span["name"])

    def test_no_secret_or_query_string_in_any_egress_span(self):
        for span in self.spans:
            if span["name"].startswith("egress_"):
                blob = json.dumps(span["attributes"])
                self.assertNotIn(TOKEN, blob, span["name"])
                self.assertNotIn("token=", blob, span["name"])
                self.assertNotIn("#frag", blob, span["name"])
                for key in ("input.value", "output.value"):
                    self.assertNotIn("?", span["attributes"][key], span["name"])


class TheSpanInputIsTheDecisionToo(unittest.TestCase):
    def test_check_record_has_exactly_the_four_fields(self):
        decision = egress.Decision(True, ["93.184.216.34"], "", False, "public address")
        self.assertEqual(egress.check_record("shop.example", 443, decision),
                         {"host": "shop.example", "port": 443, "decision": "allowed", "reason": "public address"})

    def test_a_decision_with_no_code_still_has_a_reason(self):
        decision = egress.Decision(False, [], "x", False)
        self.assertEqual(egress.check_record("h", 80, decision)["reason"], "unknown")
        self.assertEqual(egress.check_record("h", 80, decision)["decision"], "unresolved")


if __name__ == "__main__":
    unittest.main()
