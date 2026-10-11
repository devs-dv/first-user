"""Supabase access for the job queue: runs, steps, frictions and screenshots.

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment (worker/.env).
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from supabase import AsyncClient, acreate_client

BUCKET = "screenshots"

_client: AsyncClient | None = None


async def client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await acreate_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    return _client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def enqueue_run(url: str, goal: str, source: str = "live", start_url: str | None = None) -> dict:
    row = {"url": url, "goal": goal, "source": source}
    if start_url:
        row["start_url"] = start_url
    response = await (await client()).table("runs").insert(row).execute()
    return response.data[0]


async def claim_run() -> dict | None:
    """Take the oldest queued run and mark it running, or return None if the queue is empty."""
    response = await (await client()).rpc("claim_run").execute()
    return response.data[0] if response.data else None


async def add_step(
    run_id: str,
    idx: int,
    tool: str,
    thought: str,
    input: dict,
    result: dict,
    url: str | None,
    screenshot_path: str | None = None,
) -> None:
    await (await client()).table("steps").insert({
        "run_id": run_id,
        "idx": idx,
        "tool": tool,
        "thought": thought,
        "input": input,
        "result": result,
        "url": url,
        "screenshot_path": screenshot_path,
    }).execute()


async def add_friction(
    run_id: str,
    step_idx: int | None,
    kind: str,
    severity: str | None,
    expected: str,
    happened: str,
) -> None:
    await (await client()).table("frictions").insert({
        "run_id": run_id,
        "step_idx": step_idx,
        "kind": kind,
        "severity": severity,
        "expected": expected,
        "happened": happened,
    }).execute()


async def finish_run(run_id: str, result: dict, agent_version: str, brain_model: str) -> None:
    await _update_run(run_id, {
        "status": "done",
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "result": result,
        "cost_usd": result.get("usage", {}).get("estimated_cost_usd", {}).get("total"),
        "agent_version": agent_version,
        "brain_model": brain_model,
        "trace_id": result.get("trace_id"),
        "first_impression": result.get("first_impression"),
        "entry": result.get("entry"),
        "findings": result.get("findings"),
        "finished_at": _now(),
    })


# Columns added after the first schema. If the database does not have one yet (supabase/schema.sql
# not re-run), runs are saved without it and a warning is printed once, rather than failing.
OPTIONAL_COLUMNS = ("trace_id", "first_impression", "entry", "findings")
_missing_columns: set[str] = set()


async def _update_run(run_id: str, update: dict) -> None:
    update = {k: v for k, v in update.items() if k not in _missing_columns}
    try:
        await (await client()).table("runs").update(update).eq("id", run_id).execute()
    except Exception as error:
        missing = {c for c in OPTIONAL_COLUMNS if c in update and c in str(error)}
        if not missing:
            raise
        _missing_columns.update(missing)
        print(f"runs.{', runs.'.join(sorted(missing))} does not exist yet (run the last lines of "
              "supabase/schema.sql); saving runs without it.", flush=True)
        update = {k: v for k, v in update.items() if k not in _missing_columns}
        await (await client()).table("runs").update(update).eq("id", run_id).execute()


async def take_run_secrets(run_id: str) -> dict | None:
    """Read a run's test login and delete it from the database in the same statement.

    Returns {"email", "password"} or None if the run has none. After this call the database no
    longer holds the login; it lives only in the worker's memory for the run.
    """
    response = await (await client()).rpc("take_run_secrets", {"p_run_id": run_id}).execute()
    row = response.data[0] if response.data else None
    return {"email": row["test_email"], "password": row["test_password"]} if row else None


async def delete_run_secrets(run_id: str) -> None:
    """Safety net at the end of a run, whatever happened: no test login stays behind."""
    try:
        await (await client()).table("run_secrets").delete().eq("run_id", run_id).execute()
    except Exception as error:
        print(f"Could not clear the test login for run {run_id}: {type(error).__name__}", flush=True)


async def delete_old_run_secrets(minutes: int = 30) -> None:
    """A test login whose run was never claimed (or never finished) is not kept."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    try:
        await (await client()).table("run_secrets").delete().lt("created_at", cutoff).execute()
    except Exception:
        pass


async def fail_run(
    run_id: str,
    error: str,
    agent_version: str | None = None,
    brain_model: str | None = None,
    result: dict | None = None,
) -> None:
    update = {"status": "failed", "error": error[:2000], "finished_at": _now()}
    if agent_version:
        update["agent_version"] = agent_version
    if brain_model:
        update["brain_model"] = brain_model
    if result is not None:
        update.update({
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "result": result,
            "cost_usd": result.get("usage", {}).get("estimated_cost_usd", {}).get("total"),
            "trace_id": result.get("trace_id"),
            "first_impression": result.get("first_impression"),
            "entry": result.get("entry"),
            "findings": result.get("findings"),
        })
    await _update_run(run_id, update)


async def fail_stale_runs(minutes: int = 15) -> list[dict]:
    """Mark runs that have been running for longer than `minutes` as failed."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    response = await (await client()).table("runs").update({
        "status": "failed",
        "error": f"Stale: still running after {minutes} minutes (worker stopped or crashed).",
        "finished_at": _now(),
    }).eq("status", "running").lt("started_at", cutoff).execute()
    return response.data


async def upload_screenshot(run_id: str, local_path: Path) -> str:
    """Upload a PNG or JPEG to the public screenshots bucket and return its public URL."""
    storage_path = f"{run_id}/{local_path.name}"
    bucket = (await client()).storage.from_(BUCKET)
    content_type = "image/jpeg" if local_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    await bucket.upload(
        storage_path,
        local_path.read_bytes(),
        {"content-type": content_type, "x-upsert": "true"},
    )
    return await bucket.get_public_url(storage_path)


class RunRecorder:
    """Writes one run's steps, frictions and screenshots to Supabase as they happen."""

    def __init__(self, run_id: str):
        self.run_id = run_id

    def __repr__(self) -> str:
        return f"RunRecorder(run_id={self.run_id!r})"

    async def upload_screenshot(self, path: Path) -> str:
        """Upload one step's screenshot; do() calls this so the URL can go into its span output."""
        return await upload_screenshot(self.run_id, path)

    async def first_impression(self, review: dict) -> None:
        """Save the first-impression review as soon as it is written, so the live page can show it."""
        await _update_run(self.run_id, {"first_impression": review})

    async def step(self, idx, tool, thought, input, result, url, screenshot_url: str | None) -> None:
        await add_step(self.run_id, idx, tool, thought, input, result, url, screenshot_url)

    async def friction(self, step_idx, kind, severity, expected, happened) -> None:
        await add_friction(self.run_id, step_idx, kind, severity, expected, happened)
