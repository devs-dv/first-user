"""Tests that secrets and screenshots never reach exported telemetry.

Usage: python -m unittest test_trace_safety -v

Spans go through neatlogs' own MaskingSpanExporter (the component that applies
`neatlogs.init(mask=...)` at export time) into an in-memory exporter, so the assertions
are about what would arrive at neatlogs. Fake keys are assembled from parts at run time,
so this file contains no key-shaped string. No network, no model calls.
"""

import ast
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from neatlogs.core.masking_exporter import MaskingSpanExporter
from neatlogs.decorators._base import _safe_json_dumps
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

import trace_media
import trace_safety

HERE = Path(__file__).parent
BODY = "FAKEFAKEFAKE0123456789abcdefABCDEF"
FAKE_ANTHROPIC = "sk" + "-" + "ant" + "-" + "api03" + "-" + BODY
FAKE_OTHER_SK = "sk" + "-" + "proj" + "-" + BODY
FAKE_JWT = ".".join(["eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "eyJ" + "yb2xlIjoic2VydmljZV9yb2xlIn0", "FAKESIGNATUREFAKESIGNATURE"])
FAKE_SB_SECRET = "sb" + "_" + "secret" + "_" + BODY
FAKE_NEATLOGS = "plainlooking" + "NEATLOGSkey" + "0123456789"  # no recognisable shape at all
PNG_B64 = "iVBORw0KGgo" + "A" * 4000  # long inline image data


class FakeClient:
    """What a traced function receives when it is handed an API client."""

    def __init__(self):
        self.api_key = FAKE_ANTHROPIC
        self.base_url = "https://api.anthropic.com"
        self.timeout = 600


class FakeConfig:
    def __init__(self):
        self.supabase_url = "https://example.supabase.co"
        self.service_role_key = FAKE_JWT
        self.model = "claude-haiku-5-5"


def export(attributes=None, *, events=None, status=None, name="span") -> dict:
    """Run one span through the masking exporter and return what it exported."""
    sink = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(MaskingSpanExporter(sink, trace_safety.mask)))
    span = provider.get_tracer("test").start_span(name, attributes=attributes or {})
    for event_name, event_attributes in events or []:
        span.add_event(event_name, event_attributes)
    if status:
        span.set_status(status)
    span.end()
    provider.shutdown()
    exported = sink.get_finished_spans()
    assert len(exported) == 1, "the span was dropped"
    return {
        "name": exported[0].name,
        "attributes": dict(exported[0].attributes),
        "events": [(e.name, dict(e.attributes)) for e in exported[0].events],
        "status": exported[0].status,
    }


def everything(exported: dict) -> str:
    return json.dumps(exported, default=str)


class SecretsAreRedacted(unittest.TestCase):
    def assertRedacted(self, exported: dict, *secrets: str):
        text = everything(exported)
        for secret in secrets:
            self.assertNotIn(secret, text)
        self.assertIn("[redacted]", text)

    def test_a_client_passed_as_a_traced_argument(self):
        # Exactly what the @neatlogs.span decorator records for judge(client, ...).
        captured = _safe_json_dumps({"client": FakeClient(), "case_id": "saucedemo_locked_out"})
        self.assertIn(FAKE_ANTHROPIC, captured, "the fake client must reproduce the leak")
        exported = export({"neatlogs.tool.input": captured, "input.value": captured})
        self.assertRedacted(exported, FAKE_ANTHROPIC)
        self.assertIn("saucedemo_locked_out", everything(exported))

    def test_a_config_object(self):
        exported = export({"input.value": _safe_json_dumps({"config": FakeConfig()})})
        self.assertRedacted(exported, FAKE_JWT)
        self.assertIn("claude-haiku-5-5", everything(exported))

    def test_key_shaped_strings_in_free_text(self):
        text = f"call failed with key {FAKE_ANTHROPIC}, other {FAKE_OTHER_SK}, jwt {FAKE_JWT}, sb {FAKE_SB_SECRET}"
        exported = export({"output.value": text})
        self.assertRedacted(exported, FAKE_ANTHROPIC, FAKE_OTHER_SK, FAKE_JWT, FAKE_SB_SECRET)

    def test_fields_named_like_secrets(self):
        attributes = {
            "llm.api_key": "not-key-shaped-but-named-api-key",
            "input.value": json.dumps({
                "headers": {"authorization": "Bearer xyz", "x-api-key": "short", "Content-Type": "application/json"},
                "token": "abc", "password": "hunter2", "secret": "s3", "key": "plain",
            }),
        }
        exported = export(attributes)
        text = everything(exported)
        for value in ("not-key-shaped-but-named-api-key", "Bearer xyz", "short", "abc", "hunter2", "s3"):
            self.assertNotIn(f'"{value}"', text.replace("\\", ""))
        self.assertEqual(exported["attributes"]["llm.api_key"], "[redacted]")
        self.assertIn("application/json", text)

    def test_header_text_form(self):
        bearer = "Bearer " + "abcdef" + "1234567890"
        exported = export({"output.value": f"request headers: x-api-key: abcdef123456 and Authorization: {bearer}"})
        self.assertNotIn("abcdef123456", everything(exported))
        self.assertNotIn("1234567890", everything(exported))

    def test_secret_environment_values_of_any_shape(self):
        with mock.patch.dict(os.environ, {"NEATLOGS_API_KEY": FAKE_NEATLOGS, "UNRELATED": "plainvalue12345"}):
            exported = export({"output.value": f"used {FAKE_NEATLOGS} and plainvalue12345"})
        text = everything(exported)
        self.assertNotIn(FAKE_NEATLOGS, text)
        self.assertIn("plainvalue12345", text, "only secret-named variables are redacted")

    def test_exception_events_and_status(self):
        message = f"AuthenticationError: invalid x-api-key {FAKE_ANTHROPIC}"
        exported = export(
            events=[("exception", {"exception.message": message, "exception.stacktrace": message})],
            status=Status(StatusCode.ERROR, message),
        )
        self.assertNotIn(FAKE_ANTHROPIC, everything(exported))

    def test_span_names(self):
        self.assertNotIn(FAKE_ANTHROPIC, everything(export(name=f"call {FAKE_ANTHROPIC}")))

    def test_secret_next_to_a_screenshot(self):
        image_block = json.dumps([{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG_B64}},
                                  {"type": "text", "text": f"key {FAKE_ANTHROPIC}"}])
        exported = export({"neatlogs.llm.input_messages.1.content": image_block})
        text = everything(exported)
        self.assertNotIn(FAKE_ANTHROPIC, text)
        self.assertNotIn(PNG_B64, text)
        self.assertIn("screenshot omitted from trace", text)


class OrdinaryTelemetryIsKept(unittest.TestCase):
    def test_counts_names_and_text_survive(self):
        attributes = {
            "neatlogs.llm.token_count.prompt": 1200,
            "neatlogs.llm.max_tokens": 2048,
            "neatlogs.llm.prompt_key": "first-visit-test/persona_prompt",
            "neatlogs.llm.tools.0.name": "note_friction",
            "output.value": json.dumps({"outcome": "gave_up", "steps": 7, "reason": "The token counter page loaded."}),
            "neatlogs.llm.input_messages.0.content": "You are visiting a website for the first time.",
            "run_id": "6f2a07e5-9d50-4855-885f-67fa0a872bf9",
        }
        exported = export(attributes)
        self.assertEqual(exported["attributes"], attributes)

    def test_is_secret_name(self):
        for name in ("api_key", "API-Key", "x-api-key", "token", "password", "Authorization", "secret",
                     "access_token", "SUPABASE_SERVICE_ROLE_KEY", "client_secret", "key"):
            self.assertTrue(trace_safety.is_secret_name(name), name)
        for name in ("max_tokens", "token_count", "prompt_key", "keyboard", "input_tokens", "tokenizer", "name"):
            self.assertFalse(trace_safety.is_secret_name(name), name)


# Argument names that mean "this may carry a secret or a live object".
SENSITIVE_ARGUMENTS = {
    "client", "config", "cfg", "settings", "env", "environ", "credentials", "creds", "secret", "secrets",
    "token", "api_key", "key", "headers", "session", "ctx", "context", "recorder", "stagehand", "browser",
    "guard", "page", "usage", "publish",
}


def _traced_functions():
    files = sorted(HERE.glob("*.py")) + [HERE.parent / "evals" / "run.py"]
    for path in files:
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                call = decorator if isinstance(decorator, ast.Call) else None
                target = call.func if call else decorator
                if isinstance(target, ast.Attribute) and target.attr == "span" or (
                    isinstance(target, ast.Name) and target.id == "span"
                ):
                    capture_off = bool(call) and any(
                        k.arg == "capture_input" and isinstance(k.value, ast.Constant) and k.value.value is False
                        for k in call.keywords
                    )
                    yield path.name, node, capture_off


class TracedFunctionsDoNotReceiveSecrets(unittest.TestCase):
    def test_no_traced_function_takes_a_client_or_live_object(self):
        found = list(_traced_functions())
        self.assertGreater(len(found), 10, "the scan should find the traced functions")
        offenders = []
        for filename, node, capture_off in found:
            arguments = [a.arg for a in node.args.args + node.args.kwonlyargs]
            risky = sorted(set(arguments) & SENSITIVE_ARGUMENTS)
            if risky and not capture_off:
                offenders.append(f"{filename}:{node.name}({', '.join(risky)})")
        self.assertEqual(offenders, [], "traced functions receive objects that can carry secrets; "
                                        "pass plain values or set capture_input=False")

    def test_the_functions_that_take_objects_record_their_input_explicitly(self):
        sources = {name: (HERE / name).read_text(encoding="utf-8") for name in ("browse.py", "visit.py", "verifier.py", "first_impression.py")}
        for name, source in sources.items():
            self.assertIn("capture_input=False", source, name)
            self.assertIn("trace_safety.set_input(", source, name)

    def test_the_mask_is_installed_where_neatlogs_is_initialised(self):
        for path in [*HERE.glob("main.py"), HERE / "run_once.py", HERE / "check_costs.py",
                     HERE.parent / "evals" / "run.py"]:
            self.assertIn("mask=trace_safety.mask", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
