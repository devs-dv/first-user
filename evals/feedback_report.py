"""What visitors said about the findings: counts, the false-positive rate and, if there is retest data, how
many findings voted "fixed" a later retest also labelled Fixed.

Usage: python evals/feedback_report.py

Reads finding_feedback (one vote per finding per visitor). A false positive is a vote of "not a real
problem"; the rate is those votes divided by all votes.

Retest data is runs.retest of a Check again run (worker/retest.py): {"labels": [{"finding_index": n,
"label": "fixed" | "still_present" | "not_reached" | "inconclusive", ...}], "new": [...], "original_run_id":
...}. `finding_index` is the position in the ORIGINAL run's findings, and a vote's finding_id is that
finding's id by the rule of findingIds() in web/lib/feedback-logic.ts (its own valid `id`, else "f<index>"),
so a "fixed" vote on the original run is matched to the label of the same finding in its latest retest. If
the runs.retest column does not exist yet, the line says "not available yet".
"""

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "worker"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "worker" / ".env")

VERDICTS = ("useful", "not_a_problem", "fixed")
LABELS = {"useful": "useful", "not_a_problem": "not a real problem", "fixed": "fixed"}
PAGE = 1000
# Same pattern as FINDING_ID in web/lib/feedback-logic.ts (a test keeps them equal).
FINDING_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def summarise(votes: list[dict], retests: dict[tuple[str, str], str] | None) -> dict:
    """Counts and rates from vote rows ({run_id, finding_id, verdict}). `retests` maps (run_id, finding_id)
    to the label a later retest gave it, or is None when there is no retest data."""
    counts = {verdict: sum(1 for v in votes if v.get("verdict") == verdict) for verdict in VERDICTS}
    total = sum(counts.values())
    summary = {
        "counts": counts,
        "total": total,
        "false_positive_rate": (counts["not_a_problem"] / total) if total else None,
        "fixed_confirmed": None,
        "fixed_votes_retested": None,
    }
    if retests is not None:
        fixed = {(v["run_id"], v["finding_id"]) for v in votes if v.get("verdict") == "fixed"}
        retested = [key for key in fixed if key in retests]
        summary["fixed_votes_retested"] = len(retested)
        summary["fixed_confirmed"] = sum(1 for key in retested if str(retests[key]).lower() == "fixed")
    return summary


def render(summary: dict) -> str:
    counts, total = summary["counts"], summary["total"]
    lines = ["Feedback on findings", ""]
    lines += [f"  {LABELS[verdict]:<20} {counts[verdict]}" for verdict in VERDICTS]
    lines += [f"  {'all votes':<20} {total}", ""]
    rate = summary["false_positive_rate"]
    lines.append("False-positive rate (not a real problem / all votes): "
                 + ("n/a, no votes yet" if rate is None else f"{rate:.0%} ({counts['not_a_problem']} of {total})"))
    if summary["fixed_confirmed"] is None:
        lines.append("Findings voted fixed that a later retest labelled Fixed: not available yet")
    else:
        lines.append("Findings voted fixed that a later retest labelled Fixed: "
                     f"{summary['fixed_confirmed']} of {summary['fixed_votes_retested']} retested "
                     f"({counts['fixed']} voted fixed in all)")
    return "\n".join(lines)


async def read_votes(client) -> list[dict]:
    votes, start = [], 0
    while True:
        page = (await client.table("finding_feedback").select("run_id, finding_id, verdict")
                .range(start, start + PAGE - 1).execute()).data
        votes += page
        if len(page) < PAGE:
            return votes
        start += PAGE


def finding_ids(findings: list | None) -> list[str]:
    """The id of each finding, as findingIds() in web/lib/feedback-logic.ts has it: a finding's own valid
    `id` string, otherwise "f" and its position."""
    ids = []
    for index, finding in enumerate(findings or []):
        own = finding.get("id") if isinstance(finding, dict) else None
        ids.append(own if isinstance(own, str) and FINDING_ID.match(own) else f"f{index}")
    return ids


def retest_labels(retest_rows: list[dict], originals: dict[str, list | None]) -> dict[tuple[str, str], str]:
    """Label by (original run id, finding id) from Check again runs.

    `retest_rows` are runs that have a retest ({"retest_of", "retest", "finished_at"}); `originals` maps an
    original run id to its findings. When an original was checked more than once, the latest retest wins.
    """
    labels: dict[tuple[str, str], str] = {}
    for row in sorted(retest_rows, key=lambda r: str(r.get("finished_at") or r.get("created_at") or "")):
        retest = row.get("retest")
        if not isinstance(retest, dict):
            continue
        original_id = retest.get("original_run_id") or row.get("retest_of")
        if original_id not in originals:
            continue
        ids = finding_ids(originals[original_id])
        for item in retest.get("labels") or []:
            index = item.get("finding_index") if isinstance(item, dict) else None
            if isinstance(index, int) and 0 <= index < len(ids) and item.get("label"):
                labels[(original_id, ids[index])] = str(item["label"])
    return labels


async def read_retests(client) -> dict[tuple[str, str], str] | None:
    """Retest labels by (original run id, finding id), or None when runs has no retest column (yet)."""
    try:
        rows = (await client.table("runs").select("id, retest_of, retest, created_at, finished_at")
                .not_.is_("retest", "null").execute()).data
    except Exception:
        return None
    original_ids = sorted({(r.get("retest") or {}).get("original_run_id") or r.get("retest_of") for r in rows}
                          - {None})
    originals: dict[str, list | None] = {}
    for start in range(0, len(original_ids), 100):
        chunk = original_ids[start:start + 100]
        found = (await client.table("runs").select("id, findings").in_("id", chunk).execute()).data
        originals.update({r["id"]: r.get("findings") for r in found})
    return retest_labels(rows, originals)


async def main() -> None:
    import db

    client = await db.client()
    votes = await read_votes(client)
    print(render(summarise(votes, await read_retests(client))))


if __name__ == "__main__":
    asyncio.run(main())
