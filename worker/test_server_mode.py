"""Tests for running on a server: health lines, graceful shutdown, Chrome launch options, the image.

Usage: python -m unittest test_server_mode -v
No browser, no model, no network.
"""

import test_support  # noqa: F401  (first: keeps tests from sending traces to neatlogs)
import asyncio
import contextlib
import io
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import browser
import config
import worker_loop
import worker_run

HERE = Path(__file__).parent


class FakeDb:
    def __init__(self, runs=()):
        self.runs = list(runs)
        self.claims = 0

    async def claim_run(self, worker_id=None):
        self.claims += 1
        self.worker_ids = getattr(self, "worker_ids", []) + [worker_id]
        return self.runs.pop(0) if self.runs else None

    async def fail_stale_runs(self, minutes):
        return []

    async def delete_old_run_secrets(self, minutes):
        return None


def make_worker(db, execute, **kwargs):
    kwargs.setdefault("health_interval", 0.3)
    kwargs.setdefault("heartbeat_seconds", 0.05)
    kwargs.setdefault("idle_seconds", 0.05)
    return worker_loop.Worker("abc1234", db=db, execute=execute, brain_model="claude-test", **kwargs)


async def never(run, agent_version):
    raise AssertionError("no run was expected")


class HealthLines(unittest.IsolatedAsyncioTestCase):
    async def run_for(self, worker, seconds):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            task = asyncio.create_task(worker.run())
            await asyncio.sleep(seconds)
            worker.request_stop("test")
            await asyncio.wait_for(task, 3)
        return out.getvalue()

    async def test_an_idle_worker_logs_a_health_line_each_interval(self):
        text = await self.run_for(make_worker(FakeDb(), never), 1.1)
        lines = [l for l in text.splitlines() if l.startswith("[health]")]
        self.assertGreaterEqual(len(lines), 2)
        self.assertLessEqual(len(lines), 5)
        for line in lines:
            self.assertIn("idle", line)
            self.assertIn("queue empty", line)
            self.assertIn("0 runs since start", line)
            self.assertIn("agent abc1234", line)
            self.assertRegex(line, r"^\[health\] \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ idle ")

    async def test_no_health_line_while_a_run_is_in_progress(self):
        async def slow(run, agent_version):
            await asyncio.sleep(1.0)

        worker = make_worker(FakeDb([{"id": "r1"}]), slow, health_interval=0.2)
        text = await self.run_for(worker, 0.9)
        self.assertEqual([l for l in text.splitlines() if l.startswith("[health]")], [])
        self.assertEqual(worker.state, "stopping")

    async def test_the_heartbeat_file_is_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "heartbeat"
            worker = make_worker(FakeDb(), never, health_file=str(path))
            await self.run_for(worker, 0.3)
            self.assertTrue(path.exists())
            self.assertLess(time.time() - path.stat().st_mtime, 5)


class GracefulShutdown(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved = {name: signal.getsignal(getattr(signal, name))
                      for name in ("SIGINT", "SIGTERM") if hasattr(signal, name)}

    def tearDown(self):
        for name, handler in self.saved.items():
            signal.signal(getattr(signal, name), handler)

    async def test_sigterm_while_idle_exits_promptly(self):
        worker = make_worker(FakeDb(), never)
        worker.install_signal_handlers()
        out = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stdout(out):
            task = asyncio.create_task(worker.run())
            await asyncio.sleep(0.2)
            signal.raise_signal(signal.SIGTERM)
            await asyncio.wait_for(task, 3)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertIn("SIGTERM", out.getvalue())
        self.assertTrue(worker.stop_requested)

    async def test_sigterm_during_a_run_finishes_and_saves_it_first(self):
        saved = []
        db = FakeDb([{"id": "r1"}, {"id": "r2"}])

        async def execute(run, agent_version):
            await asyncio.sleep(1.0)
            saved.append(run["id"])

        worker = make_worker(db, execute)
        worker.install_signal_handlers()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            task = asyncio.create_task(worker.run())
            await asyncio.sleep(0.4)
            signal.raise_signal(signal.SIGTERM)
            await asyncio.wait_for(task, 5)
        self.assertEqual(saved, ["r1"], "the run in progress was finished and saved")
        self.assertEqual(db.claims, 1, "no further run was claimed after the signal")
        self.assertEqual(worker.runs_done, 1)

    async def test_a_second_signal_stops_immediately(self):
        worker = make_worker(FakeDb(), never)
        worker.install_signal_handlers()
        with contextlib.redirect_stdout(io.StringIO()):
            signal.raise_signal(signal.SIGTERM)
            with self.assertRaises(KeyboardInterrupt):
                signal.raise_signal(signal.SIGTERM)

    async def test_handlers_are_installed_for_sigterm_and_sigint(self):
        worker = make_worker(FakeDb(), never)
        worker.install_signal_handlers()
        self.assertEqual(signal.getsignal(signal.SIGTERM), worker.on_signal)
        self.assertEqual(signal.getsignal(signal.SIGINT), worker.on_signal)


class ChromeLaunchOptions(unittest.TestCase):
    def options(self, **settings):
        with mock.patch.multiple(browser, **settings):
            return browser.launch_options("http://127.0.0.1:9999", 9222)

    def test_server_settings(self):
        options = self.options(HEADLESS=True, CHROME_SANDBOX=False, VIEWPORT_WIDTH=1280, VIEWPORT_HEIGHT=800,
                               DEVICE_SCALE_FACTOR=1.0)
        self.assertTrue(options["headless"])
        self.assertIs(options["chromium_sandbox"], False)
        self.assertEqual((options["viewport_width"], options["viewport_height"]), (1280, 800))
        self.assertEqual(options["device_scale_factor"], 1.0)
        self.assertEqual(options["proxy_server"], "http://127.0.0.1:9999")
        self.assertEqual(options["proxy_bypass"], "<-loopback>")
        self.assertIn("--force-webrtc-ip-handling-policy=disable_non_proxied_udp", options["args"])
        self.assertIn("--disable-gpu", options["args"])

    def test_local_defaults_keep_a_window_and_the_sandbox(self):
        options = self.options(HEADLESS=False, CHROME_SANDBOX=True)
        self.assertFalse(options["headless"])
        self.assertIsNone(options["chromium_sandbox"])
        self.assertNotIn("--disable-gpu", options["args"])

    def test_a_small_shm_adds_the_flag_and_a_large_one_does_not(self):
        small = mock.Mock(total=64 * 1024 * 1024)
        large = mock.Mock(total=1024 * 1024 * 1024)
        with mock.patch.object(browser.shutil, "disk_usage", return_value=small):
            self.assertIn("--disable-dev-shm-usage", browser.chrome_args(headless=True))
        with mock.patch.object(browser.shutil, "disk_usage", return_value=large):
            self.assertNotIn("--disable-dev-shm-usage", browser.chrome_args(headless=True))
        with mock.patch.object(browser.shutil, "disk_usage", side_effect=FileNotFoundError):
            self.assertNotIn("--disable-dev-shm-usage", browser.chrome_args(headless=True))

    def test_flag_parsing(self):
        for text, expected in (("true", True), ("TRUE", True), ("1", True), ("yes", True), ("false", False),
                               ("0", False), ("", False)):
            with mock.patch.dict(os.environ, {"X_FLAG": text}):
                self.assertEqual(config._flag("X_FLAG", not expected), expected, text)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("X_FLAG", None)
            self.assertTrue(config._flag("X_FLAG", True))


class HealthCheckScript(unittest.TestCase):
    def run_check(self, path, **extra):
        env = {**os.environ, "HEALTH_FILE": str(path), **extra}
        return subprocess.run([sys.executable, str(HERE / "healthcheck.py")], env=env, capture_output=True,
                              text=True).returncode

    def test_fresh_stale_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "heartbeat"
            self.assertEqual(self.run_check(path), 1, "no file")
            path.touch()
            self.assertEqual(self.run_check(path), 0, "fresh")
            old = time.time() - 600
            os.utime(path, (old, old))
            self.assertEqual(self.run_check(path), 1, "stale")


class RunFiles(unittest.TestCase):
    def test_local_files_are_removed_only_when_asked(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(worker_run, "RUNS_DIR", Path(folder)):
                for flag, should_exist in ((False, True), (True, False)):
                    run_dir = Path(folder) / "run-1"
                    run_dir.mkdir(exist_ok=True)
                    (run_dir / "step_1.png").write_bytes(b"x")
                    with mock.patch.object(worker_run, "CLEAN_RUN_FILES", flag):
                        worker_run._clean_run_files("run-1")
                    self.assertEqual(run_dir.exists(), should_exist, f"CLEAN_RUN_FILES={flag}")


class ImageHoldsNoSecrets(unittest.TestCase):
    def test_dockerfile_and_ignore_file(self):
        dockerfile = (HERE / "Dockerfile").read_text(encoding="utf-8")
        ignore = (HERE / ".dockerignore").read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"(?m)^USER \S+")
        self.assertNotRegex(dockerfile, r"(?m)^USER (root|0)\b")
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("HEADLESS=true", dockerfile)
        self.assertNotRegex(dockerfile, r"(?i)(api_key|secret|password|token|service_role)\s*=\s*\S")
        self.assertNotRegex(dockerfile, r"(?im)^\s*(COPY|ADD)\s+.*\.env")
        for pattern in (".env", ".venv", "runs", ".git"):
            self.assertIn(pattern, ignore.split(), pattern)

    def test_the_chrome_sandbox_is_not_switched_off_in_the_image(self):
        dockerfile = (HERE / "Dockerfile").read_text(encoding="utf-8")
        env_lines = [line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")]
        self.assertFalse([line for line in env_lines if "CHROME_SANDBOX" in line])
        self.assertFalse([line for line in env_lines if "no-sandbox" in line])
        self.assertNotRegex(dockerfile, r"(?m)^\s*ENV\s+.*\bCI=")


class ChromeSeccompProfile(unittest.TestCase):
    def test_the_profile_is_the_default_plus_one_allow_rule(self):
        import json

        profile = json.loads((HERE / "chrome-seccomp.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["defaultAction"], "SCMP_ACT_ERRNO")
        last = profile["syscalls"][-1]
        self.assertEqual(last, {"names": ["clone", "unshare", "setns", "chroot"], "action": "SCMP_ACT_ALLOW"})
        # Nothing broader than the namespace calls was added anywhere.
        everything = {name for rule in profile["syscalls"] if rule.get("action") == "SCMP_ACT_ALLOW"
                      and not rule.get("includes") and not rule.get("args") and not rule.get("excludes")
                      for name in rule.get("names", [])}
        for dangerous in ("mount", "pivot_root", "ptrace", "bpf", "kexec_load", "init_module", "reboot"):
            self.assertNotIn(dangerous, everything, dangerous)

    def test_the_generator_refuses_an_allow_everything_source(self):
        import make_chrome_seccomp

        with self.assertRaises(SystemExit):
            make_chrome_seccomp.build({"defaultAction": "SCMP_ACT_ALLOW", "syscalls": []})


class BrowserPreflight(unittest.TestCase):
    def run_preflight(self, **patches):
        import asyncio

        import browser

        async def fine():
            class Page:
                async def evaluate(self, script):
                    return 2
            return object(), object(), Page(), object()

        async def close(*args):
            return None

        values = {"open_browser": fine, "close_browser": close}
        values.update(patches)
        with mock.patch.multiple(browser, **values):
            return asyncio.run(browser.browser_preflight())

    def test_a_working_browser_reports_ok(self):
        import browser

        with mock.patch.object(browser, "CHROME_SANDBOX", True), mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CI", None)
            ok, message = self.run_preflight()
        self.assertTrue(ok)
        self.assertIn("browser ok", message)

    def test_a_disabled_sandbox_is_reported_as_a_warning(self):
        import browser

        with mock.patch.object(browser, "CHROME_SANDBOX", False):
            ok, message = self.run_preflight()
        self.assertTrue(ok)
        self.assertIn("WARNING", message)
        self.assertIn("sandbox is OFF", message)

    def test_ci_in_the_environment_is_reported(self):
        import browser

        with mock.patch.object(browser, "CHROME_SANDBOX", True), mock.patch.dict("os.environ", {"CI": "1"}):
            ok, message = self.run_preflight()
        self.assertIn("CI is set", message)

    def test_a_browser_that_cannot_start_fails_with_the_fix(self):
        async def broken():
            raise RuntimeError("No usable sandbox! Update your kernel")

        ok, message = self.run_preflight(open_browser=broken)
        self.assertFalse(ok)
        self.assertIn("No usable sandbox", message)
        self.assertIn("chrome-seccomp.json", message)
        self.assertIn("DEPLOY.md", message)


if __name__ == "__main__":
    unittest.main()
