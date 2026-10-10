"""Run one first-time visitor against a URL.

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

load_dotenv(Path(__file__).parent / ".env")

neatlogs.init(api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-visit-test")

from browse import run_persona  # noqa: E402
from browser import close_browser, open_browser  # noqa: E402
from tools import RunContext  # noqa: E402


@neatlogs.span(kind="WORKFLOW", name="first_visit")
async def first_visit(url: str, goal: str, run_id: str) -> dict:
    browser, stagehand, page = await open_browser()
    try:
        await page.goto(url)
        ctx = RunContext(url=url, goal=goal, run_id=run_id, stagehand=stagehand, page=page)
        return await run_persona(ctx)
    finally:
        await close_browser(browser, stagehand)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one first-time visitor against a web app.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Run {run_id}: {args.url}", flush=True)
    try:
        result = asyncio.run(first_visit(args.url, args.goal, run_id))
        print(json.dumps({"run_id": run_id, **result}, indent=2))
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
