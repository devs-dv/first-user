"""What visitors said about the findings: counts, the false-positive rate and, if there is retest data, how
many findings voted "fixed" a later retest also labelled Fixed.

Usage: python evals/feedback_report.py

Reads finding_feedback (one vote per finding per visitor). A false positive is a vote of "not a real
problem"; the rate is those votes divided by all votes. Retest data is read from runs.retest if that column
exists (provisional shape: a list of {"finding_id": ..., "label": "Fixed" | ...}); until the retest feature
writes it, the line says "not available yet".
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "worker"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "worker" / ".env")

VERDICTS = ("useful", "not_a_problem", "fixed")
LABELS = {"useful": "useful", "not_a_problem": "not a real problem", "fixed": "fixed"}
PAGE = 1000


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


async def read_retests(client) -> dict[tuple[str, str], str] | None:
    """Retest labels by (run_id, finding_id), or None when the runs table has no retest data (yet)."""
    try:
        rows = (await client.table("runs").select("id, retest").not_.is_("retest", "null").execute()).data
    except Exception:
        return None
    labels: dict[tuple[str, str], str] = {}
    for row in rows:
        for item in row.get("retest") or []:
            if isinstance(item, dict) and item.get("finding_id") and item.get("label"):
                labels[(row["id"], str(item["finding_id"]))] = str(item["label"])
    return labels or None


async def main() -> None:
    import db

    client = await db.client()
    votes = await read_votes(client)
    print(render(summarise(votes, await read_retests(client))))


if __name__ == "__main__":
    asyncio.run(main())
