"""Browser tools the visitor agent can call, plus their Anthropic tool schemas."""

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import neatlogs
from pydantic import BaseModel, Field

from config import ACT_TIMEOUT_MS

RUNS_DIR = Path(__file__).parent / "runs"
MAX_INTERACTIVE = 15
SCROLL_PIXELS = 700


@dataclass
class RunContext:
    url: str
    goal: str
    run_id: str
    stagehand: Any
    page: Any
    screenshots: int = 0
    frictions: list[dict] = field(default_factory=list)
    finished: dict | None = None

    @property
    def run_dir(self) -> Path:
        return RUNS_DIR / self.run_id


# Set by run_persona so tool functions take only the arguments the model sends.
current_run: ContextVar[RunContext] = ContextVar("current_run")


async def _active_page():
    ctx = current_run.get()
    return await ctx.stagehand.browser.context.active_page() or ctx.page


class VisibleContent(BaseModel):
    summary: str = Field(
        description=(
            "Two or three sentences describing what a first-time visitor sees on the page: "
            "headings, main content, and any visible instructions, credentials, errors or messages."
        )
    )


@neatlogs.span(kind="TOOL", tool_name="look")
async def look() -> dict:
    ctx = current_run.get()
    page = await _active_page()
    extracted = await ctx.stagehand.extract(
        "Describe what a first-time visitor sees on this page.",
        VisibleContent,
        page=page,
    )
    observed = await ctx.stagehand.observe(
        "find the links, buttons, form fields and menus a visitor could interact with",
        page=page,
    )
    return {
        "url": await page.url(),
        "title": await page.title(),
        "summary": extracted.data.summary,
        "interactive": [
            {"description": action.description, "method": action.method}
            for action in observed.data[:MAX_INTERACTIVE]
        ],
    }


@neatlogs.span(kind="TOOL", tool_name="do")
async def do(instruction: str) -> dict:
    ctx = current_run.get()
    page = await _active_page()
    try:
        result = await ctx.stagehand.act(instruction, page=page, timeout=ACT_TIMEOUT_MS)
        success, message = result.data.success, result.data.message
    except Exception as error:
        success, message = False, f"{type(error).__name__}: {error}"[:500]

    page = await _active_page()
    ctx.screenshots += 1
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=ctx.run_dir / f"step_{ctx.screenshots}.png")
    return {"success": success, "message": message, "url": await page.url()}


@neatlogs.span(kind="TOOL", tool_name="scroll")
async def scroll(direction: str) -> dict:
    page = await _active_page()
    delta = SCROLL_PIXELS if direction == "down" else -SCROLL_PIXELS
    await page.scroll(400, 300, 0, delta)
    position = json.loads(
        await page.evaluate(
            "JSON.stringify({scroll_y: Math.round(window.scrollY), viewport_height: window.innerHeight,"
            " page_height: document.documentElement.scrollHeight})"
        )
    )
    return {"url": await page.url(), **position}


@neatlogs.span(kind="TOOL", tool_name="go_back")
async def go_back() -> dict:
    page = await _active_page()
    await page.go_back()
    return {"url": await page.url()}


@neatlogs.span(kind="TOOL", tool_name="note_friction")
async def note_friction(severity: str, expected: str, happened: str) -> dict:
    ctx = current_run.get()
    page = await _active_page()
    friction = {
        "severity": severity,
        "expected": expected,
        "happened": happened,
        "url": await page.url(),
    }
    ctx.frictions.append(friction)
    return {"recorded": True, "total_frictions": len(ctx.frictions)}


@neatlogs.span(kind="TOOL", tool_name="finish")
async def finish(outcome: str, reason: str) -> dict:
    ctx = current_run.get()
    ctx.finished = {"outcome": outcome, "reason": reason}
    return {"finished": True}


TOOL_FUNCTIONS = {
    "look": look,
    "do": do,
    "scroll": scroll,
    "go_back": go_back,
    "note_friction": note_friction,
    "finish": finish,
}

_THOUGHT = {
    "type": "string",
    "description": (
        "One complete first-person sentence saying what you notice and why you are taking this action, "
        "e.g. \"I can see a login form with demo usernames listed below it, so I'll type the first one.\""
    ),
}


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"thought": _THOUGHT, **properties},
        "required": ["thought", *required],
        "additionalProperties": False,
    }


TOOL_SCHEMAS = [
    {
        "name": "look",
        "description": (
            "Look at the current page. Returns the URL, the title, a short summary of what is visible, "
            "and up to 15 things you could interact with. Call this whenever the page may have changed."
        ),
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "do",
        "description": (
            "Perform ONE single-step action on the page, such as clicking one button or typing text into one field. "
            "Name the element the way a visitor would see it. Returns success, a message and the URL afterwards."
        ),
        "input_schema": _schema(
            {
                "instruction": {
                    "type": "string",
                    "description": "One atomic action, e.g. \"click the 'Sign up' button\" or \"type 'jane' into the username field\".",
                }
            },
            ["instruction"],
        ),
        "strict": True,
    },
    {
        "name": "scroll",
        "description": "Scroll the page by about one screen. Returns the new scroll position and page height.",
        "input_schema": _schema(
            {"direction": {"type": "string", "enum": ["up", "down"]}},
            ["direction"],
        ),
        "strict": True,
    },
    {
        "name": "go_back",
        "description": "Press the browser's back button.",
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "note_friction",
        "description": (
            "Record a moment where you were confused, slowed down or blocked, before you try something else."
        ),
        "input_schema": _schema(
            {
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "low: a small annoyance. medium: you had to work around it. high: it stopped you.",
                },
                "expected": {"type": "string", "description": "What you expected to see or happen."},
                "happened": {"type": "string", "description": "What actually happened."},
            },
            ["severity", "expected", "happened"],
        ),
        "strict": True,
    },
    {
        "name": "finish",
        "description": "End the visit. Call this exactly once, when you reach the goal or stop trying.",
        "input_schema": _schema(
            {
                "outcome": {
                    "type": "string",
                    "enum": ["achieved", "gave_up", "blocked"],
                    "description": (
                        "achieved: you reached the goal. gave_up: a real visitor would leave here. "
                        "blocked: the site prevented you from continuing (an error, a wall, or a payment step)."
                    ),
                },
                "reason": {"type": "string", "description": "One or two sentences explaining the outcome."},
            },
            ["outcome", "reason"],
        ),
        "strict": True,
    },
]
