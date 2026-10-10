"""Measure how reliably browser actions take effect on saucedemo, with no brain model.

Usage: python measure_clicks.py --mode plain|ladder [--attempts 5]

plain:  one stagehand.act(instruction) per step (the old do() behaviour)
ladder: tools.do(instruction), with its no-effect check and recovery ladder
Each attempt uses a fresh browser: log in, then add one item to the cart.
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from browser import close_browser, open_browser  # noqa: E402
from config import ACT_TIMEOUT_MS  # noqa: E402
from tools import RUNS_DIR, RunContext, current_run, do, page_fingerprint  # noqa: E402

URL = "https://www.saucedemo.com"
STEPS = [
    "type 'standard_user' into the username field",
    "type 'secret_sauce' into the password field",
    "click the Login button",
    "click the 'Add to cart' button for Sauce Labs Backpack",
]
BADGE_JS = "document.querySelector('.shopping_cart_badge')?.textContent || ''"


async def plain_step(stagehand, page, instruction: str) -> dict:
    before = await page_fingerprint(page)
    try:
        result = await stagehand.act(instruction, page=page, timeout=ACT_TIMEOUT_MS)
        reported = result.data.success
    except Exception as error:
        reported = False
        print(f"    act raised {type(error).__name__}: {str(error)[:120]}")
    await page.wait_for_timeout(700)
    return {"reported_success": reported, "changed": await page_fingerprint(page) != before}


async def attempt(mode: str, run_id: str, number: int) -> dict:
    browser, stagehand, page = await open_browser()
    try:
        await page.goto(URL)
        await page.wait_for_selector("#user-name")
        ctx = RunContext(url=URL, goal="measure", run_id=f"{run_id}-{number}", stagehand=stagehand, page=page)
        token = current_run.set(ctx)
        steps = []
        try:
            for instruction in STEPS:
                if mode == "plain":
                    step = await plain_step(stagehand, page, instruction)
                else:
                    result = await do(instruction)
                    step = {
                        "reported_success": result["success"],
                        "changed": result["changed"],
                        "rung": result.get("rung"),
                    }
                steps.append({"instruction": instruction, **step})
                print(f"  attempt {number}: {instruction!r} -> {step}", flush=True)
        finally:
            current_run.reset(token)
        logged_in = "inventory" in await page.url()
        badge = await page.evaluate(BADGE_JS) if logged_in else ""
        metrics = await stagehand.metrics()
        return {
            "attempt": number,
            "steps": steps,
            "logged_in": logged_in,
            "item_in_cart": badge == "1",
            "stagehand_tokens": int(metrics.total_prompt_tokens + metrics.total_completion_tokens),
        }
    finally:
        await close_browser(browser, stagehand)


async def main(mode: str, attempts: int) -> None:
    run_id = f"measure-{mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    results = [await attempt(mode, run_id, n) for n in range(1, attempts + 1)]
    step_total = sum(len(r["steps"]) for r in results)
    summary = {
        "mode": mode,
        "attempts": attempts,
        "end_to_end_success": sum(r["logged_in"] and r["item_in_cart"] for r in results),
        "steps_that_changed_page": f"{sum(s['changed'] for r in results for s in r['steps'])}/{step_total}",
        "steps_reported_success_but_no_change": sum(
            s["reported_success"] and not s["changed"] for r in results for s in r["steps"]
        ),
        "stagehand_tokens": sum(r["stagehand_tokens"] for r in results),
        "results": results,
    }
    RUNS_DIR.mkdir(exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["plain", "ladder"], required=True)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.attempts))
