"""Queue one run for the worker, without the web app.

Usage: python enqueue.py --url URL --goal "GOAL" [--source manual]
"""

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert a queued run.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()

    run = asyncio.run(db.enqueue_run(args.url, args.goal, args.source))
    print(f"Queued run {run['id']} ({run['status']}): {run['url']}")


if __name__ == "__main__":
    main()
