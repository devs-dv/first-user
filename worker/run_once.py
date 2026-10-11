"""Run one first-time visitor against a URL, with no database.

Usage: python run_once.py --url URL --goal "GOAL"
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import neatlogs
from dotenv import load_dotenv

import trace_safety

load_dotenv(Path(__file__).parent / ".env")

neatlogs.init(api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-visit-test", mask=trace_safety.mask)

from config import BRAIN_EFFORT, BRAIN_MODEL  # noqa: E402
from visit import first_visit  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one first-time visitor against a web app.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Run {run_id}: {args.url} (brain {BRAIN_MODEL}, effort {BRAIN_EFFORT})", flush=True)
    try:
        result = asyncio.run(first_visit(args.url, args.goal, run_id))
        print(json.dumps({"run_id": run_id, **result}, indent=2))
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
