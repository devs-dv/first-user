"""Execute one claimed "understand" run: read the site, write the brief, save it on the run.

Kept apart from worker_run.py (which dispatches here for runs of kind "understand") so the path can be
tested with a stand-in database. The brief is saved on the run itself (runs.brief); a site that could
not be read still gets a message the web page can show.
"""

import traceback

import neatlogs

import db
import trace_safety
from understand import UNDERSTAND_MODEL, SiteUnreadable, understand_site


async def _update(run_id: str, update: dict) -> None:
    await (await db.client()).table("runs").update(update).eq("id", run_id).execute()


async def execute_understand(run: dict, agent_version: str, *, understand=understand_site, update=_update) -> None:
    run_id = run["id"]
    print(f"Claimed understand run {run_id}: {run['url']} (model {UNDERSTAND_MODEL}, agent {agent_version})",
          flush=True)
    base = {"agent_version": agent_version, "brain_model": UNDERSTAND_MODEL}

    # While the run works, `brief` holds where it is ({"status": "reading" | "writing", "pages_read": n}) for
    # the waiting page. The finished brief or the failure below replaces it.
    async def progress(state: dict) -> None:
        await update(run_id, {"brief": state})

    try:
        with neatlogs.identify(session_id=f"run_{run_id}"):
            result = await understand(run["url"], run_id, progress=progress)
    except SiteUnreadable as error:
        message = trace_safety.scrub(str(error))
        await update(run_id, {**base, "status": "failed", "error": message[:2000], "finished_at": db._now(),
                              "brief": {"status": "could_not_read", "message": message}})
        print(f"Understand run {run_id}: could not read the site", flush=True)
        return
    except Exception as error:
        message = trace_safety.scrub(f"{type(error).__name__}: {error}")
        print(trace_safety.scrub(traceback.format_exc()), flush=True)
        await update(run_id, {**base, "status": "failed", "error": message[:2000], "finished_at": db._now(),
                              "brief": {"status": "could_not_read",
                                        "message": "Something went wrong while writing the brief. Please try again."}})
        print(f"Understand run {run_id} failed: {type(error).__name__}", flush=True)
        return
    try:
        await update(run_id, {**base, "status": "done", "brief": result["brief"], "cost_usd": result["cost_usd"],
                              "result": {"usage": result["usage"]}, "finished_at": db._now()})
    except Exception as error:
        # Most likely supabase/schema.sql ("Understand mode") has not been run: say so, do not lose the run.
        print(f"Could not save the brief for run {run_id}: {type(error).__name__}: {error}", flush=True)
        await db.fail_run(run_id, "Could not save the brief (has the 'Understand mode' SQL been run?)",
                          agent_version, UNDERSTAND_MODEL)
        return
    print(f"Understand run {run_id} done: {len(result['brief']['claims'])} claims, "
          f"{len(result['brief']['suggested_journeys'])} journeys, ${result['cost_usd']}", flush=True)
