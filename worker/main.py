"""Queue worker: claim queued runs from Supabase and execute them one at a time.

Usage: python main.py
SIGTERM (what `docker stop` sends), Ctrl+C or Ctrl+Break once: finish the current run, then exit.
A second signal stops immediately (the run is left "running" and a later stale-run sweep marks it
failed). While idle it logs a health line once a minute.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import neatlogs
from dotenv import load_dotenv

import trace_safety

load_dotenv(Path(__file__).parent / ".env")

# This process owns the stop signals so it can finish the current run first; it shuts neatlogs down
# itself. mask redacts secrets and keeps screenshots out of exported traces; the model still gets
# the screenshots (trace_safety.py, trace_media.py).
neatlogs.init(
    api_key=os.environ["NEATLOGS_API_KEY"],
    workflow_name="first-visit-test",
    register_shutdown_handlers=False,
    mask=trace_safety.mask,
)

import db  # noqa: E402
from config import BRAIN_MODEL, HEALTH_FILE, HEALTH_INTERVAL_SECONDS  # noqa: E402
from worker_loop import Worker  # noqa: E402
from worker_run import execute  # noqa: E402


def _agent_version() -> str:
    """The version label saved on each run: AGENT_VERSION (set when the image is built), else git."""
    if os.environ.get("AGENT_VERSION"):
        return os.environ["AGENT_VERSION"]
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


AGENT_VERSION = _agent_version()


def check_browser() -> bool:
    """Start Chrome once before taking any work, so a broken setup is reported at once."""
    if os.environ.get("SKIP_BROWSER_PREFLIGHT"):
        return True
    from browser import browser_preflight

    ok, message = asyncio.run(browser_preflight())
    print(f"[preflight] {message}", flush=True)
    return ok


def main() -> None:
    if not check_browser():
        print("[preflight] The worker will not start without a working browser. "
              "(SKIP_BROWSER_PREFLIGHT=1 skips this check.)", flush=True)
        neatlogs.shutdown()
        sys.exit(3)
    worker = Worker(
        AGENT_VERSION, db=db, execute=execute, brain_model=BRAIN_MODEL,
        health_interval=HEALTH_INTERVAL_SECONDS, health_file=HEALTH_FILE,
    )
    worker.install_signal_handlers()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        print("Stopped immediately.", flush=True)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
        print("Worker stopped.", flush=True)


if __name__ == "__main__":
    main()
