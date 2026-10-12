"""The facts of how a report was made, shown in a collapsed panel on the report page.

Everything here is counted from the run, not written by a model: steps taken, the actions that needed
a recovery and on which rung, our own issues, page reloads, the page errors recorded, the independent
check's verdict and quote, the cost and the time. Added to afterwards, in worker_run, with what only
the worker knows (agent version, worker id, trace id).
"""

import time

# A recovery rung is any rung after the first: b (observe, then act), c (the located element), d (mouse).
RUNG_WORDS = {"a": "act on the instruction", "b": "observe then act", "c": "locator", "d": "mouse click"}
MAX_ERRORS = 8


def build_run_facts(ctx, finished: dict, verification: dict | None, steps_taken: int) -> dict:
    recoveries = []
    page_errors: list[str] = []
    for entry in ctx.record:
        if entry["tool"] != "do":
            continue
        rung = entry.get("rung")
        if rung in ("b", "c", "d"):
            recoveries.append({"step": entry["step"], "rung": rung, "how": RUNG_WORDS[rung],
                               "instruction": entry.get("instruction", "")[:120]})
        for error in entry.get("page_errors") or []:
            if error not in page_errors:
                page_errors.append(error)
    verification = verification or {}
    return {
        "steps_taken": steps_taken,
        "recoveries": recoveries,
        "own_issues": [{"step": issue.get("step"), "instruction": issue.get("instruction", "")[:120],
                        "reason": issue.get("reason")} for issue in ctx.agent_issues],
        "page_reloads": getattr(ctx, "page_reloads", 0),
        "page_errors": page_errors[:MAX_ERRORS],
        "page_error_count": len(page_errors),
        "verifier": ({"verdict": verification.get("verdict"), "quote": verification.get("reason", "")[:500]}
                     if verification else None),
        "success_condition": getattr(ctx, "success_condition", None),
        "checked_without_success_condition": not getattr(ctx, "success_condition", None),
        "cost_usd": round(ctx.usage.total_cost, 5),
        "duration_seconds": round(time.time() - getattr(ctx, "started_at", time.time()), 1),
    }
