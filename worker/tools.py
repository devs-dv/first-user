"""Browser tools the visitor agent can call, plus their Anthropic tool schemas."""

import functools
import hashlib
import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import neatlogs
from opentelemetry import trace as otel_trace
from pydantic import BaseModel, Field

from config import ACT_TIMEOUT_MS
from costs import RunUsage, stagehand_cost

RUNS_DIR = Path(__file__).parent / "runs"
MAX_INTERACTIVE = 15
MAX_SUMMARY_CHARS = 400
MAX_ITEM_CHARS = 80


def clip(text: str, limit: int) -> str:
    """Shorten text to at most `limit` characters at a word boundary, ending with an ellipsis."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:  # a very long single word is cut where it is
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "\u2026"
SCROLL_PIXELS = 700
SETTLE_CHECKS_MS = (400, 400, 800)


@dataclass
class RunContext:
    url: str
    goal: str
    run_id: str
    stagehand: Any
    page: Any
    screenshots: int = 0
    frictions: list[dict] = field(default_factory=list)
    agent_issues: list[dict] = field(default_factory=list)
    usage: RunUsage = field(default_factory=RunUsage)
    last_look: tuple[str, dict] | None = None
    finished: dict | None = None
    # Optional sink for steps, frictions and screenshots (db.RunRecorder); None for local runs.
    recorder: Any = None
    tool_calls: int = 0
    last_screenshot: Path | None = None
    # The browser's egress guard (egress.EgressGuard); a refused request ends the run.
    egress: Any = None

    @property
    def run_dir(self) -> Path:
        return RUNS_DIR / self.run_id


# Set by run_persona so tool functions take only the arguments the model sends.
current_run: ContextVar[RunContext] = ContextVar("current_run")


async def _active_page():
    ctx = current_run.get()
    return await ctx.stagehand.browser.context.active_page() or ctx.page


async def current_url() -> str:
    return await (await _active_page()).url()


# Visible text plus form state, so typing into a field counts as a change.
_FINGERPRINT_JS = """JSON.stringify([
  document.body ? document.body.innerText : '',
  Array.from(document.querySelectorAll('input, textarea, select'))
    .map(el => (el.type === 'checkbox' || el.type === 'radio') ? String(el.checked) : el.value)
])"""


async def page_fingerprint(page) -> str:
    """URL plus a hash of visible text and form values; no model call."""
    url = await page.url()
    try:
        state = await page.evaluate(_FINGERPRINT_JS)
    except Exception:
        state = ""
    return f"{url}#{hashlib.sha256(str(state).encode()).hexdigest()[:16]}"


async def _changed_since(before: str) -> bool:
    """Wait briefly for the page to react, then compare fingerprints."""
    for wait_ms in SETTLE_CHECKS_MS:
        page = await _active_page()
        await page.wait_for_timeout(wait_ms)
        if await page_fingerprint(await _active_page()) != before:
            return True
    return False


def metered(function):
    """Record the Stagehand tokens a tool used as attributes on its (enclosing) neatlogs span."""

    @functools.wraps(function)
    async def wrapper(*args, **kwargs):
        ctx = current_run.get()
        before = await ctx.stagehand.metrics()
        try:
            return await function(*args, **kwargs)
        finally:
            after = await ctx.stagehand.metrics()
            ctx.usage.set_stagehand(after)
            prompt = int(after.total_prompt_tokens - before.total_prompt_tokens)
            completion = int(after.total_completion_tokens - before.total_completion_tokens)
            cached = int(after.total_cached_input_tokens - before.total_cached_input_tokens)
            span = otel_trace.get_current_span()
            span.set_attribute("stagehand.prompt_tokens", prompt)
            span.set_attribute("stagehand.completion_tokens", completion)
            span.set_attribute("stagehand.cached_input_tokens", cached)
            span.set_attribute("stagehand.cost_usd", round(stagehand_cost(prompt, completion, cached), 6))

    return wrapper


class LookContent(BaseModel):
    summary: str = Field(
        description=(
            "Two or three sentences describing what a first-time visitor sees on the page: "
            "headings, main content, and any visible instructions, credentials, errors or messages."
        )
    )
    interactive: list[str] = Field(
        description=(
            "Up to 15 short labels for things a visitor could click, type into or select, "
            "most prominent first, e.g. 'Login button', 'Username field', 'Cart icon (2 items)'."
        )
    )


@neatlogs.span(kind="TOOL", tool_name="look")
@metered
async def look() -> dict:
    ctx = current_run.get()
    page = await _active_page()
    fingerprint = await page_fingerprint(page)
    if ctx.last_look and ctx.last_look[0] == fingerprint:
        return {
            "url": await page.url(),
            "unchanged": True,
            "note": "The page has not changed since your last look; that result still applies.",
        }

    content = (await ctx.stagehand.extract(
        "Describe what a first-time visitor sees on this page and list what they could interact with.",
        LookContent,
        page=page,
    )).data
    result = {
        "url": await page.url(),
        "title": await page.title(),
        "summary": clip(content.summary, MAX_SUMMARY_CHARS),
        "interactive": [clip(item, MAX_ITEM_CHARS) for item in content.interactive[:MAX_INTERACTIVE]],
    }
    ctx.last_look = (fingerprint, result)
    return result


@neatlogs.span(kind="TOOL", name="do.rung_a_act")
async def _rung_act_instruction(instruction: str) -> dict:
    ctx = current_run.get()
    result = await ctx.stagehand.act(instruction, page=await _active_page(), timeout=ACT_TIMEOUT_MS)
    return {"reported_success": result.data.success, "message": result.data.message}


@neatlogs.span(kind="TOOL", name="do.rung_b_observe_act")
async def _rung_observe_then_act(instruction: str) -> dict:
    ctx = current_run.get()
    page = await _active_page()
    observed = await ctx.stagehand.observe(instruction, page=page)
    if not observed.data:
        return {"reported_success": False, "message": "observe found no matching element", "action": None}
    action = observed.data[0]
    result = await ctx.stagehand.act(action, page=page, timeout=ACT_TIMEOUT_MS)
    return {
        "reported_success": result.data.success,
        "message": result.data.message,
        "action": {"selector": action.selector, "method": action.method, "arguments": action.arguments or []},
    }


@neatlogs.span(kind="TOOL", name="do.rung_c_locator")
async def _rung_locator(action: dict, before: str) -> dict:
    """Replay the observed element through the page locator API, without coordinates where possible."""
    locator = (await _active_page()).locator(action["selector"])
    method, arguments = action["method"], action["arguments"]
    if method in ("fill", "type") and arguments:
        await locator.fill(arguments[0])
        return {"reported_success": True, "via": "locator.fill"}
    if method == "selectOptionFromDropdown" and arguments:
        await locator.select_option(arguments[0])
        return {"reported_success": True, "via": "locator.select_option"}
    if method == "click":
        await locator.click()
        if await _changed_since(before):
            return {"reported_success": True, "via": "locator.click"}
        # A DOM click event needs no screen coordinates.
        await locator.send_click_event()
        return {"reported_success": True, "via": "locator.send_click_event"}
    return {"reported_success": False, "via": f"unsupported method {method!r}"}


@neatlogs.span(kind="TOOL", tool_name="do")
@metered
async def do(instruction: str) -> dict:
    ctx = current_run.get()
    before = await page_fingerprint(await _active_page())
    rungs: list[dict] = []
    worked = None
    action = None

    for name in ("a", "b", "c"):
        if name == "c" and action is None:
            rungs.append({"rung": "c", "skipped": "no observed element to replay"})
            continue
        try:
            if name == "a":
                outcome = await _rung_act_instruction(instruction)
            elif name == "b":
                outcome = await _rung_observe_then_act(instruction)
                action = outcome.pop("action")
            else:
                outcome = await _rung_locator(action, before)
        except Exception as error:
            outcome = {"reported_success": False, "error": f"{type(error).__name__}: {error}"[:300]}
        outcome["changed"] = await _changed_since(before)
        rungs.append({"rung": name, **outcome})
        if outcome["changed"]:
            worked = name
            break

    page = await _active_page()
    ctx.screenshots += 1
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    ctx.last_screenshot = ctx.run_dir / f"step_{ctx.screenshots}.png"
    await page.screenshot(path=ctx.last_screenshot)
    url = await page.url()
    span = otel_trace.get_current_span()
    span.set_attribute("do.rung", worked or "none")
    if worked == "c":
        span.set_attribute("do.via", rungs[-1].get("via") or "")

    if worked:
        result = {"success": True, "changed": True, "rung": worked, "url": url}
        if worked == "c":
            result["via"] = rungs[-1].get("via")
        if worked != "a":
            result["note"] = "The first try had no effect; a retry worked."
        return result

    reported_any = any(r.get("reported_success") for r in rungs)
    reason = "no_effect" if reported_any else "failed"
    ctx.agent_issues.append({"instruction": instruction, "reason": reason, "url": url, "rungs": rungs})
    return {
        "success": False,
        "changed": False,
        "reason": reason,
        "rung": None,
        "url": url,
        "message": (
            "Your action had NO EFFECT: after three different tries, the URL, visible text and form fields "
            "are exactly the same as before. The browser tool may have failed to operate that element; "
            "this was recorded as an agent issue, so do not record it as site friction on its own. "
            "Try a differently worded instruction or another way to reach your goal."
        ),
    }


@neatlogs.span(kind="TOOL", tool_name="scroll")
@metered
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
@metered
async def go_back() -> dict:
    page = await _active_page()
    await page.go_back()
    return {"url": await page.url()}


@neatlogs.span(kind="TOOL", tool_name="note_friction")
@metered
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
@metered
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
            "and up to 15 things you could interact with. If the page has not changed since your last look, "
            "it says so instead of repeating the result. Call this when the page may have changed."
        ),
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "do",
        "description": (
            "Perform ONE single-step action on the page, such as clicking one button or typing text into one field. "
            "Name the element the way a visitor would see it. Returns success, whether the page changed, and the URL "
            "afterwards. success=false with reason 'no_effect' means nothing on the page changed."
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
