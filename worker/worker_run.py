"""Execute one claimed run: load its test login, run the visit, save the outcome, clear the login.

Kept apart from main.py (which initialises neatlogs and owns the signal handlers when it is
imported) so that the whole path can be tested with a stand-in database.
"""

import traceback

import neatlogs

import db
import trace_safety
from config import BRAIN_MODEL
from credentials import TestCredentials
from visit import first_visit


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


async def execute(run: dict, agent_version: str) -> None:
    run_id = run["id"]
    start_url = run.get("start_url")
    print(f"Claimed run {run_id}: {run['url']}" + (f" (start link {start_url})" if start_url else "")
          + f" (brain {BRAIN_MODEL}, agent {agent_version})", flush=True)
    credentials, unavailable = await _take_credentials(run)
    try:
        with neatlogs.identify(session_id=f"run_{run_id}"):
            result = await first_visit(
                run["url"], run["goal"], run_id, recorder=db.RunRecorder(run_id),
                start_url=start_url, credentials=credentials, test_login_unavailable=unavailable,
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

    if result["outcome"] == "error":
        await db.fail_run(run_id, result["reason"], agent_version, BRAIN_MODEL, result=result)
        print(f"Run {run_id} failed: {result['reason'][:200]}", flush=True)
    else:
        await db.finish_run(run_id, result, agent_version, BRAIN_MODEL)
        print(f"Run {run_id} done: {result['outcome']} in {result['steps']} steps", flush=True)
