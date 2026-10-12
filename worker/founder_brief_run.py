"""Execute one claimed "founder_brief" run: read the stored product brief it points at, write the founder
brief from it, save it on this run. Fetches nothing: the pages were read when the product brief was made.

The run's brief_run_id is the product brief's run. The result is saved in this run's own `brief` column
and the page finds it by the product brief's id.
"""

import traceback

import neatlogs

import db
import trace_safety
from costs import TokenTally
from founder_brief import UNDERSTAND_MODEL, founder_brief, usable_brief


async def _update(run_id: str, update: dict) -> None:
    await (await db.client()).table("runs").update(update).eq("id", run_id).execute()


async def _load_brief(source_id: str) -> dict | None:
    rows = (await (await db.client()).table("runs").select("brief, status, kind").eq("id", source_id)
            .eq("kind", "understand").execute()).data
    return rows[0]["brief"] if rows and rows[0].get("status") == "done" else None


async def execute_founder_brief(run: dict, agent_version: str, *, load=_load_brief, write=founder_brief,
                                update=_update) -> None:
    run_id, source_id = run["id"], run.get("brief_run_id")
    print(f"Claimed founder brief run {run_id} (from brief {source_id}, model {UNDERSTAND_MODEL}, "
          f"agent {agent_version})", flush=True)
    base = {"agent_version": agent_version, "brain_model": UNDERSTAND_MODEL}

    async def fail(message: str, error: str) -> None:
        await update(run_id, {**base, "status": "failed", "error": error[:2000], "finished_at": db._now(),
                              "brief": {"status": "could_not_write", "message": message}})

    brief = await load(source_id) if source_id else None
    if not usable_brief(brief):
        await fail("There is no finished product brief to write this from.", "no usable product brief")
        print(f"Founder brief run {run_id}: no usable product brief", flush=True)
        return
    usage = TokenTally()
    try:
        with neatlogs.identify(session_id=f"run_{run_id}"):
            result = await write(brief, source_id, usage)
    except Exception as error:
        message = trace_safety.scrub(f"{type(error).__name__}: {error}")
        print(trace_safety.scrub(traceback.format_exc()), flush=True)
        await fail("Something went wrong while writing the founder brief. Please try again.", message)
        print(f"Founder brief run {run_id} failed: {type(error).__name__}", flush=True)
        return
    try:
        await update(run_id, {**base, "status": "done", "brief": result, "cost_usd": round(usage.cost, 5),
                              "result": {"usage": usage.summary()}, "finished_at": db._now()})
    except Exception as error:
        print(f"Could not save the founder brief for run {run_id}: {type(error).__name__}: {error}", flush=True)
        await db.fail_run(run_id, "Could not save the founder brief (has the founder brief SQL been run?)",
                          agent_version, UNDERSTAND_MODEL)
        return
    print(f"Founder brief run {run_id} done: {len(result['evidence_and_risks']['traction'])} stated traction, "
          f"${round(usage.cost, 5)}", flush=True)
