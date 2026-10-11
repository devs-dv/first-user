"""Run the eval set through the real queue and score the results.

Usage: python evals/run.py --version v0 [--only ID ...] [--timeout-minutes 60]

Queues every case in evals/sites.json as a run with source 'eval' (and the version
label in runs.eval_version when that column exists), waits for the worker, which
runs separately (worker/main.py), to finish them, then writes
evals/results/<version>.json and evals/results/<version>.md.

Metrics:
  completion rate    achievable cases whose outcome is "achieved" (the agent's own verdict)
  false-praise rate  broken cases whose outcome is "achieved", or whose result never
                     mentions the known issue; one claude-haiku-5-5 call per broken case
                     judges the mention, and the text it judged is printed for checking
  stopped by limit   runs that ended with stopped_by "budget" or "max_steps"
  agent issues       frictions of kind "agent_issue" across all runs
  median steps, total cost (runs, plus the judge calls)
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKER = ROOT.parent / "worker"
sys.path.insert(0, str(WORKER))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(WORKER / ".env")

import neatlogs  # noqa: E402
from anthropic import AsyncAnthropic  # noqa: E402

neatlogs.init(api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-user-evals")

import db  # noqa: E402
from costs import response_cost  # noqa: E402

JUDGE_MODEL = "claude-haiku-5-5"
POLL_SECONDS = 10
JUDGE_TOOL = {
    "name": "verdict",
    "description": "Report whether the run's result mentions the known issue.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mentions_issue": {
                "type": "boolean",
                "description": "True if the result text describes the known issue or a clear symptom of it.",
            },
            "evidence": {
                "type": "string",
                "description": "The words in the result that mention it, quoted, or an empty string.",
            },
        },
        "required": ["mentions_issue", "evidence"],
        "additionalProperties": False,
    },
}


def load_cases(only: list[str] | None) -> list[dict]:
    cases = json.loads((ROOT / "sites.json").read_text(encoding="utf-8"))["cases"]
    return [case for case in cases if not only or case["id"] in only]


async def has_eval_version_column(client) -> bool:
    try:
        await client.table("runs").select("eval_version").limit(1).execute()
        return True
    except Exception:
        return False


async def queue(client, cases: list[dict], version: str, with_label: bool) -> dict[str, str]:
    run_ids = {}
    for case in cases:
        row = {"url": case["url"], "goal": case["goal"], "source": "eval"}
        if with_label:
            row["eval_version"] = version
        inserted = (await client.table("runs").insert(row).execute()).data[0]
        run_ids[case["id"]] = inserted["id"]
        print(f"queued {case['id']}: run {inserted['id']}", flush=True)
    return run_ids


async def wait_for(client, run_ids: dict[str, str], timeout_minutes: float) -> dict[str, dict]:
    ids = list(run_ids.values())
    deadline = time.monotonic() + timeout_minutes * 60
    last: dict[str, str] = {}
    while True:
        rows = (await client.table("runs").select(
            "id,status,outcome,reason,result,error,cost_usd,agent_version,brain_model,started_at,finished_at"
        ).in_("id", ids).execute()).data
        by_id = {row["id"]: row for row in rows}
        for case_id, run_id in run_ids.items():
            state = by_id[run_id]["status"]
            if last.get(case_id) != state:
                outcome = by_id[run_id].get("outcome") or ""
                print(f"[{datetime.now():%H:%M:%S}] {case_id}: {state} {outcome}".rstrip(), flush=True)
                last[case_id] = state
        if all(row["status"] in ("done", "failed") for row in rows):
            return by_id
        if time.monotonic() > deadline:
            print(f"Timed out after {timeout_minutes} minutes; scoring the runs that finished.", flush=True)
            return by_id
        await asyncio.sleep(POLL_SECONDS)


def result_text(row: dict) -> str:
    """Everything the run reported, as the founder would read it."""
    result = row.get("result") or {}
    lines = [f"Outcome: {row.get('outcome') or 'none'} (status {row['status']})",
             f"Reason: {row.get('reason') or result.get('reason') or ''}"]
    if row["status"] == "failed" and not result:
        lines.append(f"Run error: {row.get('error') or ''}")
    for friction in result.get("frictions", []):
        lines.append(f"Friction ({friction.get('severity')}): expected {friction.get('expected')!r}; "
                     f"happened {friction.get('happened')!r}")
    for issue in result.get("agent_issues", []):
        lines.append(f"Agent issue: {issue.get('reason')} on {issue.get('instruction')!r}")
    return "\n".join(lines)


@neatlogs.span(kind="EVALUATOR", name="false_praise_judge")
async def judge(client, case_id: str, known_issue: str, text: str) -> dict:
    response = await client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        system=(
            "You check reports from an automated website tester. Given a known issue on the site and the "
            "tester's report, decide whether the report mentions that issue or a clear symptom of it. "
            "A report that only says the goal was reached does not mention it."
        ),
        messages=[{"role": "user", "content": f"Known issue:\n{known_issue}\n\nTester's report:\n{text}"}],
        tools=[JUDGE_TOOL],
        tool_choice={"type": "tool", "name": "verdict"},
    )
    verdict = next(block.input for block in response.content if block.type == "tool_use")
    return {**verdict, "cost_usd": response_cost(response)}


def score(cases: list[dict], rows: dict[str, dict], run_ids: dict[str, str],
          verdicts: dict[str, dict], agent_issue_frictions: dict[str, int]) -> tuple[list[dict], dict]:
    per_case = []
    for case in cases:
        row = rows[run_ids[case["id"]]]
        result = row.get("result") or {}
        entry = {
            "id": case["id"],
            "kind": case["kind"],
            "run_id": row["id"],
            "status": row["status"],
            "outcome": row.get("outcome"),
            "stopped_by": result.get("stopped_by"),
            "steps": result.get("steps"),
            "frictions": len(result.get("frictions", [])),
            "agent_issue_frictions": agent_issue_frictions.get(row["id"], 0),
            "cost_usd": float(row["cost_usd"]) if row.get("cost_usd") is not None else None,
            "reason": row.get("reason") or (row.get("error") or "")[:300],
        }
        if case["kind"] == "achievable":
            entry["completed"] = row.get("outcome") == "achieved"
        else:
            verdict = verdicts[case["id"]]
            entry["mentions_issue"] = verdict["mentions_issue"]
            entry["judge_evidence"] = verdict["evidence"]
            entry["false_praise"] = row.get("outcome") == "achieved" or not verdict["mentions_issue"]
        per_case.append(entry)

    achievable = [e for e in per_case if e["kind"] == "achievable"]
    broken = [e for e in per_case if e["kind"] == "broken"]
    steps = [e["steps"] for e in per_case if e["steps"] is not None]
    run_cost = sum(e["cost_usd"] or 0 for e in per_case)
    judge_cost = sum(v["cost_usd"] for v in verdicts.values())
    metrics = {
        "completion_rate": _rate(sum(e["completed"] for e in achievable), len(achievable)),
        "false_praise_rate": _rate(sum(e["false_praise"] for e in broken), len(broken)),
        "stopped_by_budget_or_step_limit": sum(e["stopped_by"] in ("budget", "max_steps") for e in per_case),
        "agent_issue_frictions": sum(e["agent_issue_frictions"] for e in per_case),
        "median_steps": statistics.median(steps) if steps else None,
        "runs_without_steps": len(per_case) - len(steps),
        "failed_runs": sum(e["status"] == "failed" for e in per_case),
        "total_cost_usd": round(run_cost + judge_cost, 5),
        "run_cost_usd": round(run_cost, 5),
        "judge_cost_usd": round(judge_cost, 5),
    }
    return per_case, metrics


def _rate(numerator: int, denominator: int) -> dict:
    return {"count": numerator, "of": denominator, "rate": round(numerator / denominator, 3) if denominator else None}


def markdown(version: str, per_case: list[dict], metrics: dict, meta: dict) -> str:
    def cell(value):
        return "" if value is None else str(value).replace("|", "\\|").replace("\n", " ")

    rows = ["| Case | Kind | Status | Outcome | Stopped by | Steps | Agent issues | Cost | Score |",
            "|---|---|---|---|---|---|---|---|---|"]
    for e in per_case:
        if e["kind"] == "achievable":
            verdict = "completed" if e["completed"] else "not completed"
        else:
            verdict = "FALSE PRAISE" if e["false_praise"] else "named the issue"
        cost = f"${e['cost_usd']:.4f}" if e["cost_usd"] is not None else ""
        rows.append(f"| {e['id']} | {e['kind']} | {e['status']} | {cell(e['outcome'])} | {cell(e['stopped_by'])} "
                    f"| {cell(e['steps'])} | {e['agent_issue_frictions']} | {cost} | {verdict} |")
    m = metrics
    summary = [
        "| Metric | Value |", "|---|---|",
        f"| Completion rate (achievable) | {m['completion_rate']['count']}/{m['completion_rate']['of']} |",
        f"| False-praise rate (broken) | {m['false_praise_rate']['count']}/{m['false_praise_rate']['of']} |",
        f"| Stopped by budget or step limit | {m['stopped_by_budget_or_step_limit']} |",
        f"| agent_issue frictions | {m['agent_issue_frictions']} |",
        f"| Median steps | {cell(m['median_steps'])} (runs without steps: {m['runs_without_steps']}) |",
        f"| Failed runs | {m['failed_runs']} |",
        f"| Total cost | ${m['total_cost_usd']:.4f} (runs ${m['run_cost_usd']:.4f}, judge ${m['judge_cost_usd']:.4f}) |",
    ]
    reasons = [f"- **{e['id']}**: {cell(e['reason'])}" for e in per_case]
    return "\n".join([
        f"# Eval {version}", "",
        f"Run {meta['finished_at']}. Agent version(s): {', '.join(meta['agent_versions']) or 'unknown'}. "
        f"Brain model(s): {', '.join(meta['brain_models']) or 'unknown'}. Judge: {JUDGE_MODEL}.", "",
        *summary, "", *rows, "", "## What each run reported", "", *reasons, "",
    ])


async def main(version: str, only: list[str] | None, timeout_minutes: float) -> None:
    cases = load_cases(only)
    client = await db.client()
    with_label = await has_eval_version_column(client)
    if not with_label:
        print("runs.eval_version does not exist yet (run the last lines of supabase/schema.sql); "
              "the version label is kept in the results file only.", flush=True)
    run_ids = await queue(client, cases, version, with_label)
    rows = await wait_for(client, run_ids, timeout_minutes)

    frictions = (await client.table("frictions").select("run_id,kind").in_(
        "run_id", list(run_ids.values())).execute()).data
    agent_issue_frictions: dict[str, int] = {}
    for friction in frictions:
        if friction["kind"] == "agent_issue":
            agent_issue_frictions[friction["run_id"]] = agent_issue_frictions.get(friction["run_id"], 0) + 1

    judge_client = neatlogs.wrap(AsyncAnthropic())
    verdicts = {}
    try:
        for case in (c for c in cases if c["kind"] == "broken"):
            text = result_text(rows[run_ids[case["id"]]])
            print(f"\n--- judge input for {case['id']} ---\nKnown issue: {case['known_issue']}\n{text}", flush=True)
            verdicts[case["id"]] = {"judged_text": text, **await judge(judge_client, case["id"], case["known_issue"], text)}
            print(f"--- verdict: mentions_issue={verdicts[case['id']]['mentions_issue']} "
                  f"evidence={verdicts[case['id']]['evidence']!r}", flush=True)
    finally:
        await judge_client.close()

    per_case, metrics = score(cases, rows, run_ids, verdicts, agent_issue_frictions)
    finished = [rows[run_id] for run_id in run_ids.values()]
    meta = {
        "version": version,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent_versions": sorted({r["agent_version"] for r in finished if r.get("agent_version")}),
        "brain_models": sorted({r["brain_model"] for r in finished if r.get("brain_model")}),
        "judge_model": JUDGE_MODEL,
        "eval_version_column": with_label,
    }
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    report = {**meta, "metrics": metrics, "cases": per_case, "judge": verdicts}
    (out_dir / f"{version}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    table = markdown(version, per_case, metrics, meta)
    (out_dir / f"{version}.md").write_text(table, encoding="utf-8")
    print("\n" + table, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue the eval cases, wait for the worker and score them.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--only", nargs="*", help="case ids to run (default: all)")
    parser.add_argument("--timeout-minutes", type=float, default=60)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.version, args.only, args.timeout_minutes))
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
