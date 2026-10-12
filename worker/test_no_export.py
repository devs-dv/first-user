"""Tests never send traces to neatlogs, and real runs and evals say which they are.

  - every test module imports test_support before anything else, so no test can start a neatlogs
    pipeline that points at the project
  - a test's spans go to a sink on this machine, even when the code asks for the real endpoint
  - real runs, evals and hand-run scripts label their root span with metadata environment=...
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)

import ast
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
ROOT = HERE.parent


class NoTestReachesNeatlogs(unittest.TestCase):
    def test_every_test_module_imports_the_guard_first(self):
        offenders = []
        for path in sorted(HERE.glob("test_*.py")):
            if path.name == "test_support.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
            first = imports[0] if imports else None
            ok = isinstance(first, ast.Import) and first.names[0].name == "test_support"
            if not ok:
                offenders.append(path.name)
        self.assertEqual(offenders, [], "these test modules do not import test_support first")

    def test_conftest_covers_pytest(self):
        text = (HERE / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("import test_support", text)

    def test_the_environment_points_at_a_local_sink_and_a_placeholder_key(self):
        endpoint = os.environ["NEATLOGS_ENDPOINT"]
        self.assertTrue(endpoint.startswith("http://127.0.0.1:"), endpoint)
        self.assertEqual(os.environ["NEATLOGS_API_KEY"], test_support.PLACEHOLDER_KEY)

    def test_loading_a_dotenv_file_cannot_bring_back_the_real_key(self):
        import tempfile

        from dotenv import load_dotenv

        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("NEATLOGS_API_KEY=a-key-from-a-file\nNEATLOGS_ENDPOINT=https://ingest.example.com\n",
                                encoding="utf-8")
            load_dotenv(env_file, override=True)
        self.assertEqual(os.environ["NEATLOGS_API_KEY"], test_support.PLACEHOLDER_KEY)
        self.assertTrue(os.environ["NEATLOGS_ENDPOINT"].startswith("http://127.0.0.1:"))

    def test_spans_reach_the_sink_even_when_the_real_endpoint_is_asked_for(self):
        # In a child process, so this test's neatlogs set-up cannot clash with another test's in this one.
        # The child inherits the sink's address; the parent's sink counts what the child sends.
        import subprocess
        import sys

        child = "\n".join([
            "import test_support",
            "import neatlogs, time",
            "neatlogs.init(api_key='a-real-looking-key', endpoint='https://ingest.neatlogs.com', "
            "workflow_name='no-export-test', register_shutdown_handlers=False)",
            "@neatlogs.span(kind='WORKFLOW', name='no_export_probe')",
            "def probe():",
            "    return 1",
            "probe()",
            "neatlogs.flush()",
            "time.sleep(1)",
            "neatlogs.shutdown()",
        ])
        before = test_support.sink_requests()
        process = subprocess.run([sys.executable, "-c", child], cwd=HERE, capture_output=True, text=True,
                                 timeout=120, env=dict(os.environ))
        self.assertEqual(process.returncode, 0, process.stderr[-800:])
        deadline = time.time() + 10
        while test_support.sink_requests() == before and time.time() < deadline:
            time.sleep(0.2)
        self.assertGreater(test_support.sink_requests(), before, "the spans were delivered to the local sink")
        self.assertNotIn("ingest.neatlogs.com", process.stderr)

    def test_real_runs_and_evals_never_import_the_guard(self):
        for path in (HERE / "main.py", HERE / "worker_run.py", HERE / "visit.py", ROOT / "evals" / "run.py"):
            self.assertNotIn("test_support", path.read_text(encoding="utf-8"), path.name)


class EnvironmentMetadata(unittest.TestCase):
    def span_metadata(self, work):
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        tracer = provider.get_tracer("t")
        with tracer.start_as_current_span("root") as span:
            work()
            return json.loads(span.attributes.get("metadata", "{}"))

    def test_set_metadata_merges_into_the_active_span(self):
        import trace_safety

        def work():
            self.assertTrue(trace_safety.set_metadata(environment="production"))
            trace_safety.set_metadata(eval_version="v6", nothing=None)

        self.assertEqual(self.span_metadata(work), {"environment": "production", "eval_version": "v6"})

    def test_no_span_means_no_metadata_and_no_error(self):
        import trace_safety

        self.assertFalse(trace_safety.set_metadata(environment="production"))

    def test_the_worker_labels_real_runs_production_and_eval_runs_eval(self):
        import asyncio

        import worker_run

        seen = []

        class FakeDb:
            async def take_run_secrets(self, run_id):
                return None

            async def delete_run_secrets(self, run_id):
                pass

            async def finish_run(self, *args, **kwargs):
                pass

            async def fail_run(self, *args, **kwargs):
                pass

            class RunRecorder:
                def __init__(self, run_id):
                    pass

        async def first_visit(url, goal, run_id, recorder=None, **kwargs):
            seen.append(kwargs.get("environment"))
            return {"outcome": "achieved", "steps": 1, "reason": "ok"}

        fake = FakeDb()
        with mock.patch.multiple(worker_run.db, take_run_secrets=fake.take_run_secrets,
                                 delete_run_secrets=fake.delete_run_secrets, finish_run=fake.finish_run,
                                 fail_run=fake.fail_run, RunRecorder=fake.RunRecorder), \
                mock.patch.object(worker_run, "first_visit", first_visit):
            for source in ("web", "live", None, "eval"):
                asyncio.run(worker_run.execute({"id": f"r-{source}", "url": "https://x.test/", "goal": "g",
                                                "source": source}, "v"))
        self.assertEqual(seen, ["production", "production", "production", "eval"])

    def test_first_visit_defaults_to_production_and_scripts_say_development(self):
        import re

        visit_source = (HERE / "visit.py").read_text(encoding="utf-8")
        self.assertIn('trace_safety.set_metadata(environment=environment or os.environ.get("FIRST_USER_ENVIRONMENT")'
                      ' or "production")', visit_source)
        for name in ("run_once.py", "check_costs.py", "check_traces.py"):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertRegex(text, r'FIRST_USER_ENVIRONMENT", "development"', name)
            self.assertLess(text.index("FIRST_USER_ENVIRONMENT"), re.search(r"^import neatlogs", text, re.M).start())

    def test_the_eval_root_span_is_labelled_eval(self):
        text = (ROOT / "evals" / "run.py").read_text(encoding="utf-8")
        self.assertIn('trace_safety.set_metadata(environment="eval"', text)
        # and it is inside the root span's function, not at import time
        self.assertLess(text.index('name="first-user-evals"'), text.index('set_metadata(environment="eval"'))


if __name__ == "__main__":
    unittest.main()
