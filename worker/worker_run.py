"""Execute one claimed run: load its test login, run the visit, save the outcome, clear the login.

Kept apart from main.py (which initialises neatlogs and owns the signal handlers when it is
imported) so that the whole path can be tested with a stand-in database.
"""

import shutil
import socket
import traceback

import neatlogs

import db
import trace_safety
from config import BRAIN_MODEL, CHECK_AGAIN, CLEAN_RUN_FILES
from credentials import TestCredentials
from tools import RUNS_DIR
from visit import first_visit


def _clean_run_files(run_id: str) -> None:
    """Delete the run's local screenshots (CLEAN_RUN_FILES): they were uploaded, and a server's disk
    would otherwise fill up. Left alone by default, for debugging on a laptop."""
    if CLEAN_RUN_FILES:
        shutil.rmtree(RUNS_DIR / run_id, ignore_errors=True)


ACCESS_MODES = ("public", "link", "account", "signup")


def access_mode_for(run: dict) -> str:
    """How the founder let the visitor in.

    Runs from the web form carry it. Runs queued before that (and from the command line) are read
    from what they have: a test login, a start link, or neither, which meant "may sign up".
    """
    mode = run.get("access_mode")
    if mode in ACCESS_MODES:
        return mode
    if run.get("has_test_login"):
        return "account"
    if run.get("start_url"):
        return "link"
    return "signup"


def access_mode_was_chosen(run: dict) -> bool:
    """False only when "signup" is the fallback for a run that carried no choice and nothing to infer one from."""
    return run.get("access_mode") in ACCESS_MODES or bool(run.get("has_test_login") or run.get("start_url"))


async def _take_credentials(run: dict):
    """The run's test login, read and deleted from the database, or (None, unavailable)."""
    if not run.get("has_test_login"):
        return None, False
    try:
        row = await db.take_run_secrets(run["id"])
    except Exception as error:
        # The type only: the message is not needed, and nothing about a login should be logged.
        print(f"Could not read the test login for run {run['id']}: {type(error).__name__}", flush=True)
        return None, True
    if row is None:
        return None, True
    credentials = TestCredentials(row["email"], row["password"])
    credentials.register()  # redacted from every span and result from this moment on
    return credentials, False


async def _load_original(run: dict) -> dict | None:
    """The original run a retest is compared with, or None for an ordinary run (or if it cannot be read).

    Only its findings, verdict, start link and recorded steps: never a test login.
    """
    original_id = run.get("retest_of")
    if not original_id or not CHECK_AGAIN:
        return None
    try:
        return await db.get_original_for_retest(original_id)
    except Exception as error:
        print(f"Could not read the original run {original_id} for run {run['id']}: {type(error).__name__}",
              flush=True)
        return None


async def execute(run: dict, agent_version: str) -> None:
    run_id = run["id"]
    start_url = run.get("start_url")
    access_mode = access_mode_for(run)
    print(f"Claimed run {run_id}: {run['url']}" + (f" (start link {start_url})" if start_url else "")
          + f" (access {access_mode}, brain {BRAIN_MODEL}, agent {agent_version})", flush=True)
    credentials, unavailable = await _take_credentials(run)
    retest = await _load_original(run)
    try:
        with neatlogs.identify(session_id=f"run_{run_id}"):
            result = await first_visit(
                run["url"], run["goal"], run_id, recorder=db.RunRecorder(run_id),
                start_url=start_url, credentials=credentials, test_login_unavailable=unavailable,
                access_mode=access_mode, access_mode_chosen=access_mode_was_chosen(run),
                success_condition=run.get("success_condition") or None, retest=retest,
                # Runs queued by evals/run.py carry source "eval"; everything else is a real run.
                environment="eval" if run.get("source") == "eval" else "production",
            )
    except Exception as error:
        # Error text and tracebacks pass through scrub(): an exception can echo what was typed.
        message = trace_safety.scrub(f"{type(error).__name__}: {error}")
        print(trace_safety.scrub(traceback.format_exc()), flush=True)
        await db.fail_run(run_id, message, agent_version, BRAIN_MODEL)
        print(f"Run {run_id} failed: {type(error).__name__}", flush=True)
        return
    finally:
        # take_run_secrets already deleted it; this is the safety net, success or failure.
        await db.delete_run_secrets(run_id)
        _clean_run_files(run_id)

    # What only the worker knows goes into the run facts: who ran it, which version, which trace.
    facts = result.get("run_facts")
    if isinstance(facts, dict):
        facts.update({
            "agent_version": agent_version,
            "worker_id": run.get("worker_id") or f"{socket.gethostname()}@{agent_version}",
            "trace_id": result.get("trace_id"),
        })
    if result["outcome"] == "error":
        await db.fail_run(run_id, result["reason"], agent_version, BRAIN_MODEL, result=result)
        print(f"Run {run_id} failed: {result['reason'][:200]}", flush=True)
    else:
        await db.finish_run(run_id, result, agent_version, BRAIN_MODEL)
        print(f"Run {run_id} done: {result['outcome']} in {result['steps']} steps", flush=True)
