"""Turn a live run into a case in evals/real_world.json.

Usage: python evals/from_run.py <run_id> --expect achieved|broken --note "what a person would see"

  --expect achieved   a visitor can really do the goal: the case is "achievable"
  --expect broken     something on the site is wrong: the case is "broken", and the note is the known
                      issue the eval's judge looks for in the run's report

Copies the run's URL, goal, access mode, start link and success condition, the expected outcome, your
note and the source run id. It never copies a test login (the case only says that it needs one) and it
refuses an address, goal or note that looks like it holds a secret. Reads one row; queues nothing.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "worker"))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "worker" / ".env")

import cases  # noqa: E402

# Never the run's secrets: run_secrets is a different table and is not read here.
COLUMNS = "id, url, goal, access_mode, start_url, has_test_login, status, kind"
OPTIONAL = ", success_condition"


async def fetch_run(run_id: str) -> dict:
    import db

    client = await db.client()
    try:
        rows = (await client.table("runs").select(COLUMNS + OPTIONAL).eq("id", run_id).execute()).data
    except Exception:  # a database from before the success condition column
        rows = (await client.table("runs").select(COLUMNS).eq("id", run_id).execute()).data
    if not rows:
        raise SystemExit(f"No run {run_id}.")
    return rows[0]


def add_to_file(case: dict, path: Path) -> int:
    document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    merged = cases.merge_case(document, case)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(merged["cases"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn a live run into a real-world eval case.")
    parser.add_argument("run_id")
    parser.add_argument("--expect", required=True, choices=cases.EXPECTATIONS)
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    row = asyncio.run(fetch_run(args.run_id))
    if row.get("kind") not in (None, "test"):
        raise SystemExit(f"Run {args.run_id} is a '{row['kind']}' run, not a test run.")
    try:
        case = cases.case_from_run(row, args.expect, args.note)
    except (ValueError, cases.NotSafeToCopy) as error:
        raise SystemExit(f"Not added: {error}")
    total = add_to_file(case, ROOT / cases.FILES["real_world"])
    print(f"Added {case['id']} ({case['kind']}) to evals/real_world.json: {total} case(s) in all.")
    if case.get("needs_test_login") or case.get("needs_start_link"):
        print("Note: this case needs a login or start link that is not stored, so evals/run.py skips it "
              "until you add one by hand.")


if __name__ == "__main__":
    main()
