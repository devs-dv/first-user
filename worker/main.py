"""Queue worker: claim queued runs from Supabase and execute them one at a time.

Usage: python main.py
Ctrl+C once: finish the current run, then exit. Ctrl+C twice: stop now (the run is
left "running" and a later stale-run sweep marks it failed).
"""

import asyncio
import os
import signal
import subprocess
import time
import traceback
from pathlib import Path

import neatlogs
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# This process owns SIGINT so it can finish the current run first; it shuts neatlogs down itself.
neatlogs.init(
    api_key=os.environ["NEATLOGS_API_KEY"],
    workflow_name="first-visit-test",
    register_shutdown_handlers=False,
)

import db  # noqa: E402
from config import BRAIN_MODEL  # noqa: E402
from visit import first_visit  # noqa: E402

IDLE_SECONDS = 2
STALE_MINUTES = 15
STALE_SWEEP_SECONDS = 60
DB_ERROR_BACKOFF_SECONDS = 10

_stop_requested = False


def _agent_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


AGENT_VERSION = _agent_version()


def _on_stop_signal(signum, frame) -> None:
    global _stop_requested
    if _stop_requested:
        raise KeyboardInterrupt
    _stop_requested = True
    print("\nStopping after the current run. Press Ctrl+C again to stop now.", flush=True)


async def _sleep_unless_stopping(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while not _stop_requested and time.monotonic() < deadline:
        await asyncio.sleep(0.2)


async def execute(run: dict) -> None:
    run_id = run["id"]
    print(f"Claimed run {run_id}: {run['url']} (brain {BRAIN_MODEL}, agent {AGENT_VERSION})", flush=True)
    try:
        with neatlogs.identify(session_id=f"run_{run_id}"):
            result = await first_visit(run["url"], run["goal"], run_id, recorder=db.RunRecorder(run_id))
    except Exception as error:
        traceback.print_exc()
        await db.fail_run(run_id, f"{type(error).__name__}: {error}", AGENT_VERSION, BRAIN_MODEL)
        print(f"Run {run_id} failed: {type(error).__name__}", flush=True)
        return

    if result["outcome"] == "error":
        await db.fail_run(run_id, result["reason"], AGENT_VERSION, BRAIN_MODEL, result=result)
        print(f"Run {run_id} failed: {result['reason'][:200]}", flush=True)
    else:
        await db.finish_run(run_id, result, AGENT_VERSION, BRAIN_MODEL)
        print(f"Run {run_id} done: {result['outcome']} in {result['steps']} steps", flush=True)


async def worker_loop() -> None:
    print(f"Worker started (agent {AGENT_VERSION}, brain {BRAIN_MODEL}). Waiting for queued runs.", flush=True)
    last_sweep = float("-inf")
    while not _stop_requested:
        try:
            if time.monotonic() - last_sweep >= STALE_SWEEP_SECONDS:
                last_sweep = time.monotonic()
                for stale in await db.fail_stale_runs(STALE_MINUTES):
                    print(f"Marked stale run {stale['id']} as failed", flush=True)
            run = await db.claim_run()
        except Exception as error:
            print(f"Database error: {type(error).__name__}: {error}; retrying in {DB_ERROR_BACKOFF_SECONDS}s", flush=True)
            await _sleep_unless_stopping(DB_ERROR_BACKOFF_SECONDS)
            continue

        if run is None:
            await _sleep_unless_stopping(IDLE_SECONDS)
            continue
        try:
            await execute(run)
        except Exception as error:
            # Saving the outcome failed; the stale-run sweep will mark the run failed later.
            print(f"Could not save run {run['id']}: {type(error).__name__}: {error}", flush=True)


def main() -> None:
    signal.signal(signal.SIGINT, _on_stop_signal)
    if hasattr(signal, "SIGBREAK"):  # Windows Ctrl+Break
        signal.signal(signal.SIGBREAK, _on_stop_signal)
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        print("Stopped immediately.", flush=True)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
        print("Worker stopped.", flush=True)


if __name__ == "__main__":
    main()
