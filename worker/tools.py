"""Browser tools the visitor agent can call, plus their Anthropic tool schemas."""

import functools
import hashlib
import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import neatlogs
from pydantic import BaseModel, Field

import page_watch
from config import ACT_TIMEOUT_MS
from costs import RunUsage
from lookup_model import lookups_nest_here

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
    # The browser's egress guard (egress.EgressGuard); a refused request ends the run.
    egress: Any = None
    # The factual record of the run for the verifier: actions, their effects and look()
    # summaries, never the agent's thoughts or conclusions (see record_step in browse.py).
    record: list[dict] = field(default_factory=list)

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


# Visible text, form state, class and ARIA state attributes and, optionally, which text field
# has focus, hashed in the page. Classes catch changes with no text (a button turning green);
# focus on a text field catches "click the search box". Focus is left out for typing actions
# (moving into an empty field is not typing into it) and for anything but text fields (a
# click on a button that does nothing does not count as a change).
_FINGERPRINT_JS = r"""((withFocus) => {
  const parts = [document.body ? document.body.innerText : ''];
  for (const el of document.querySelectorAll('input, textarea, select'))
    parts.push((el.type === 'checkbox' || el.type === 'radio') ? String(el.checked) : el.value);
  for (const el of document.querySelectorAll(
      'body [class], [aria-checked], [aria-pressed], [aria-expanded], [aria-selected]'))
    parts.push((el.getAttribute('class') || '') + '|' + (el.getAttribute('aria-checked') || '') +
      (el.getAttribute('aria-pressed') || '') + (el.getAttribute('aria-expanded') || '') +
      (el.getAttribute('aria-selected') || ''));
  const active = document.activeElement;
  if (withFocus && active && active.matches('input, textarea, select, [contenteditable=""], [contenteditable=true]'))
    parts.push('focus:' + active.tagName + '#' + active.id + '|' + (active.getAttribute('name') || ''));
  const text = parts.join('\u0001');
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) { hash ^= text.charCodeAt(i); hash = Math.imul(hash, 16777619); }
  return (hash >>> 0).toString(16) + ':' + text.length;
})(%s)"""


async def page_fingerprint(page, with_focus: bool = False) -> str:
    """URL plus a hash of what is visible and settable on the page; no model call."""
    url = await page.url()
    try:
        state = await page.evaluate(_FINGERPRINT_JS % ("true" if with_focus else "false"))
    except Exception:
        state = ""
    return f"{url}#{hashlib.sha256(str(state).encode()).hexdigest()[:16]}"


async def _changed_since(before: str, with_focus: bool = False) -> bool:
    """Wait briefly for the page to react, then compare fingerprints."""
    for wait_ms in SETTLE_CHECKS_MS:
        page = await _active_page()
        await page.wait_for_timeout(wait_ms)
        if await page_fingerprint(await _active_page(), with_focus) != before:
            return True
    return False


def metered(function):
    """Refresh the run's snapshot of Stagehand's metrics() after a tool runs.

    Lookup calls are traced as LLM spans by lookup_model.py, so token counts are not
    copied onto tool spans as custom attributes.
    """

    @functools.wraps(function)
    async def wrapper(*args, **kwargs):
        ctx = current_run.get()
        try:
            return await function(*args, **kwargs)
        finally:
            ctx.usage.set_stagehand(await ctx.stagehand.metrics())

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
@lookups_nest_here
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
        "unchanged": False,
        "summary": clip(content.summary, MAX_SUMMARY_CHARS),
        "interactive": [clip(item, MAX_ITEM_CHARS) for item in content.interactive[:MAX_INTERACTIVE]],
    }
    ctx.last_look = (fingerprint, result)
    return result


@neatlogs.span(kind="TOOL", name="do.rung_a_act")
@lookups_nest_here
async def _rung_act_instruction(instruction: str) -> dict:
    ctx = current_run.get()
    result = await ctx.stagehand.act(instruction, page=await _active_page(), timeout=ACT_TIMEOUT_MS)
    return {"reported_success": result.data.success, "message": result.data.message}


@neatlogs.span(kind="TOOL", name="do.rung_b_observe_act")
@lookups_nest_here
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
async def _rung_locator(action: dict, before: str, with_focus: bool) -> dict:
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
        if await _changed_since(before, with_focus):
            return {"reported_success": True, "via": "locator.click"}
        # A DOM click event needs no screen coordinates.
        await locator.send_click_event()
        return {"reported_success": True, "via": "locator.send_click_event"}
    return {"reported_success": False, "via": f"unsupported method {method!r}"}


# Finds the element to click for rung d, scrolls it to the middle of the viewport and returns
# its centre. With no observed element, it picks the checkbox or toggle whose surrounding text
# best matches the instruction. A checkbox drawn with zero size is clicked through its label.
_MOUSE_TARGET_JS = r"""((spec) => {
  const byXpath = (xpath) => document.evaluate(
    xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  const find = (selector) => selector.startsWith('xpath=') ? byXpath(selector.slice(6))
    : selector.startsWith('/') ? byXpath(selector) : document.querySelector(selector);
  const TOGGLES = 'input[type=checkbox], input[type=radio], [role=checkbox], [role=switch], [aria-pressed]';
  let element = spec.selector ? find(spec.selector) : null;
  let how = 'observed element';
  if (!element && spec.words.length) {
    let bestScore = 0;
    for (const candidate of document.querySelectorAll(TOGGLES)) {
      const row = candidate.closest('li, tr, label, [role=listitem], [role=row]');
      const text = [row ? row.innerText : '', candidate.getAttribute('aria-label') || '',
        candidate.id, candidate.getAttribute('class') || '', candidate.getAttribute('name') || ''].join(' ').toLowerCase();
      const score = spec.words.filter((word) => text.includes(word)).length;
      if (score > bestScore) { element = candidate; bestScore = score; }
    }
    how = 'toggle matched by its text';
  }
  if (!element) return null;
  const isToggle = element.matches(TOGGLES);
  let target = element;
  const box = element.getBoundingClientRect();
  if (isToggle && (box.width < 2 || box.height < 2)) {
    const label = (element.id && document.querySelector('label[for="' + CSS.escape(element.id) + '"]'))
      || element.closest('label')
      || (element.nextElementSibling && element.nextElementSibling.tagName === 'LABEL' ? element.nextElementSibling : null);
    if (label) { target = label; how += ', through its label'; }
  }
  target.scrollIntoView({block: 'center', inline: 'center'});
  const rect = target.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return null;
  return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, how, toggle: isToggle};
})(%s)"""

# Instructions that type text, for which focus moving into a field is not a change.
_TYPING = re.compile(r"\b(type|enter|fill|write|paste)\b", re.IGNORECASE)

# Words that mark an instruction as being about a checkbox or toggle.
_TOGGLE_WORDS = ("check", "tick", "toggle", "complete", "mark", "switch", "select", "done")
_STOP_WORDS = {"the", "and", "click", "next", "for", "into", "with", "that", "this", "box", "button", "left",
               "right", "item", "first", "one", "its", "then", "please"}


@neatlogs.span(kind="TOOL", name="do.rung_d_mouse")
async def _rung_mouse(instruction: str, action: dict | None) -> dict:
    """A trusted mouse click at the element's centre through the browser's input API.

    Rung c's DOM click event is scripted (event.isTrusted is false), and some elements
    ignore it. With no observed element, this rung looks for a checkbox or toggle that
    matches the instruction, because observe often misses visually hidden checkboxes.
    """
    page = await _active_page()
    words = []
    if any(word in instruction.lower() for word in _TOGGLE_WORDS):
        words = [w for w in re.findall(r"[a-z0-9]+", instruction.lower()) if len(w) >= 3 and w not in _STOP_WORDS]
    selector = action["selector"] if action and action["method"] in ("click", "check", "uncheck") else None
    if selector is None and not words:
        return {"reported_success": False, "via": "no element to click"}
    target = await page.evaluate(_MOUSE_TARGET_JS.replace("%s", json.dumps({"selector": selector, "words": words})))
    if not target:
        return {"reported_success": False, "via": "no element to click"}
    await page.click(target["x"], target["y"])
    return {"reported_success": True, "via": "mouse.click", "target": target["how"], "toggle": target["toggle"]}


@neatlogs.span(kind="TOOL", tool_name="do")
@metered
async def do(instruction: str) -> dict:
    ctx = current_run.get()
    page = await _active_page()
    with_focus = not _TYPING.search(instruction)
    before = await page_fingerprint(page, with_focus)
    since = await page_watch.now(page)
    rungs: list[dict] = []
    worked = None
    action = None

    for name in ("a", "b", "c", "d"):
        if name == "c" and action is None:
            rungs.append({"rung": "c", "skipped": "no observed element to replay"})
            continue
        try:
            if name == "a":
                outcome = await _rung_act_instruction(instruction)
            elif name == "b":
                outcome = await _rung_observe_then_act(instruction)
                action = outcome.pop("action")
            elif name == "c":
                outcome = await _rung_locator(action, before, with_focus)
            else:
                outcome = await _rung_mouse(instruction, action)
        except Exception as error:
            outcome = {"reported_success": False, "error": f"{type(error).__name__}: {error}"[:300]}
        outcome["changed"] = await _changed_since(before, with_focus)
        rungs.append({"rung": name, **outcome})
        if outcome["changed"]:
            worked = name
            break

    page = await _active_page()
    url = await page.url()
    page_errors = await page_watch.collect(page, since)
    screenshot_url = await _screenshot(ctx, page)

    # Every do() result has the same keys in the same order, with fixed values, so traces
    # can be searched with exact strings such as "changed": false or "kind": "agent_issue".
    if worked:
        result = {
            "success": True,
            "changed": True,
            "rung": worked,
            "via": VIA[worked] if worked in VIA else rungs[-1].get("via", "locator"),
            "reason": "worked_first_try" if worked == "a" else "worked_after_retry",
            "kind": "action",
            "url": url,
            "page_error_count": len(page_errors),
            "page_errors": page_errors,
            "message": "The action worked." if worked == "a" else RETRY_MESSAGE,
        }
    elif page_errors:
        # Nothing changed, and the page itself reported errors or failed requests while we
        # tried: that points at the site, so it is site friction, not our tool's issue.
        ctx.frictions.append({
            "kind": "site",
            "severity": "medium",
            "expected": f"'{instruction}' has a visible effect",
            "happened": "Nothing on the page changed, and the page reported errors: " + "; ".join(page_errors),
            "url": url,
            "detected_by": "page_errors",
        })
        result = {
            "success": False,
            "changed": False,
            "rung": "none",
            "via": "none",
            "reason": "page_errors",
            "kind": "site_problem",
            "url": url,
            "page_error_count": len(page_errors),
            "page_errors": page_errors,
            "message": (
                "Your action had NO EFFECT, and while it was tried the page itself reported errors "
                "(listed in page_errors). That points to a problem with the website, and it has already been "
                "recorded as site friction, so do not record it again. Decide whether a real visitor could "
                "still reach the goal another way, or conclude."
            ),
        }
    else:
        reported_any = any(r.get("reported_success") for r in rungs)
        reason = "no_effect" if reported_any else "failed"
        ctx.agent_issues.append(
            {"kind": "agent_issue", "instruction": instruction, "reason": reason, "url": url, "rungs": rungs}
        )
        result = {
            "success": False,
            "changed": False,
            "rung": "none",
            "via": "none",
            "reason": reason,
            "kind": "agent_issue",
            "url": url,
            "page_error_count": 0,
            "page_errors": [],
            "message": (
                "Your action had NO EFFECT: after four different tries, the URL, visible text and form fields "
                "are exactly the same as before, and the page reported no errors. The browser tool may have "
                "failed to operate that element; this was recorded as an agent issue, so do not record it as "
                "site friction on its own. Try a differently worded instruction or another way to reach your goal."
            ),
        }
    if screenshot_url:
        result["screenshot_url"] = screenshot_url
    return result


RETRY_MESSAGE = (
    "The action worked. Our browser tool needed a retry to operate the element: that was a problem "
    "with our tool, not with the website. A real visitor would not have noticed it, so do not record "
    "it with note_friction and do not mention it as a problem with the site."
)

# How each rung operates the element; rung c reports which locator call worked.
VIA = {"a": "act", "b": "observe_act"}


async def _screenshot(ctx: RunContext, page) -> str | None:
    """Save a screenshot of the page and, when a database is configured, upload it.

    Returns the public URL, which neatlogs shows as an image preview on the tool span,
    or None for local runs and failed uploads.
    """
    ctx.screenshots += 1
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.run_dir / f"step_{ctx.screenshots}.png"
    await page.screenshot(path=path)
    if ctx.recorder is None:
        return None
    try:
        return await ctx.recorder.upload_screenshot(path)
    except Exception as error:
        print(f"[step {ctx.tool_calls}]   !! could not upload screenshot: {type(error).__name__}: {error}", flush=True)
        return None


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
        "kind": "site",
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
    ctx.finished = {"outcome": outcome, "stopped_by": "finish", "reason": reason}
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
