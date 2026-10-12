"""Browser tools the visitor agent can call, plus their Anthropic tool schemas."""

import asyncio
import base64
import functools
import hashlib
import json
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import neatlogs
from pydantic import BaseModel, Field

import credentials as credentials_module
import bot_check
import element_state
import page_watch
import trace_media
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
# How long to watch for a page's reaction after an attempt, and how often to look. A client-side
# navigation or a request can finish a second or two after the click, so a short fixed wait
# misread slow changes as "no effect" (and the ladder then clicked again).
SETTLE_WINDOW_S = 2.0
SETTLE_POLL_S = 0.15
# Once a change is seen, wait until the page holds still this long (at most STABLE_MAX_S), so the
# screenshot and the next look see the page that was navigated to, not a transition.
STABLE_FOR_S = 0.3
STABLE_MAX_S = 1.5
# Before climbing to the next rung, wait this long and look once more.
RECHECK_WAIT_S = 1.5
# Before an attempt is recorded as an agent issue, watch this long one last time.
FINAL_CHECK_WINDOW_S = 3.0


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
    # The founder's test login (credentials.TestCredentials), or None. It only ever goes into the page
    # being tested, typed by sign_in; see credentials.py.
    credentials: Any = None
    # The start link the visit began at, when the founder gave one.
    start_url: str | None = None
    # How the founder let the visitor in: "public", "link", "account" or "signup" (worker_run.access_mode_for).
    # Only "signup" lets the visitor create an account. access_mode_chosen is False when the run carried no
    # choice and "signup" is only the fallback, so the report does not claim the founder picked it.
    access_mode: str = "signup"
    access_mode_chosen: bool = True
    # How the visit got in, and what it met on the way; read at the end of the run (browse.py).
    entry: dict = field(default_factory=lambda: {
        "test_login": "not_provided",
        "self_signup": "not_used",
        "third_party_options": [],
        "created_account_email": None,
        "login_wall_seen": False,
        # A login that was written on the page itself, typed with do(): "shown_on_page" when the typed
        # password was found in the page's text, "typed" when a password was typed that was not.
        "page_login": "not_used",
        # The login written on the page was accepted: the password field was there before the action and
        # is gone after it, on another page. Set by do().
        "page_login_worked": False,
        # The visit met a bot check ("Verify you are human") and did not try to get past it:
        # {"phrase", "url", "title", "step"}. Set by look() and do().
        "bot_check": None,
    })
    # The first-impression review, once written (first_impression.py).
    first_impression: dict | None = None
    first_impression_tried: bool = False
    # The factual record of the run for the verifier: actions, their effects and look()
    # summaries, never the agent's thoughts or conclusions (see record_step in browse.py).
    record: list[dict] = field(default_factory=list)
    # A screenshot from the latest look(), base64 PNG, sent to the brain with that result.
    pending_image: str | None = None
    # What the founder said success looks like (the form's optional field), or None. The visitor is told it,
    # and the independent check judges that condition and not only the goal's wording.
    success_condition: str | None = None
    # Page reloads made because the page's own files failed to load, and when the visit began.
    page_reloads: int = 0
    started_at: float = field(default_factory=time.time)
    # Screenshot URL and page URL of each recorded step, by step number, for the report's evidence.
    step_shots: dict[int, str] = field(default_factory=dict)
    step_urls: dict[int, str] = field(default_factory=dict)

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


async def _page_state(with_focus: bool) -> tuple[str, str] | None:
    """(url, fingerprint) of the active page, or None while it is navigating and cannot be read."""
    try:
        fingerprint = await page_fingerprint(await _active_page(), with_focus)
    except Exception:
        return None
    return fingerprint.rsplit("#", 1)[0], fingerprint


async def _changed_since(before: str, with_focus: bool = False, window: float = SETTLE_WINDOW_S) -> bool:
    """Watch the page for up to `window` seconds, and say whether it changed from `before`.

    A change is a different URL (client-side navigations included) or a different fingerprint
    (visible text, form values, classes). It returns as soon as one is seen, after waiting for the
    page to hold still. `window=0` is a single comparison.
    """
    before_url = before.rsplit("#", 1)[0]
    deadline = time.monotonic() + window
    while True:
        state = await _page_state(with_focus)
        if state is not None and (state[0] != before_url or state[1] != before):
            await _wait_until_still(with_focus, state[1])
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(SETTLE_POLL_S)


async def _wait_until_still(with_focus: bool, last: str) -> None:
    deadline = time.monotonic() + STABLE_MAX_S
    still_since = time.monotonic()
    while time.monotonic() < deadline and time.monotonic() - still_since < STABLE_FOR_S:
        await asyncio.sleep(SETTLE_POLL_S)
        state = await _page_state(with_focus)
        if state is not None and state[1] != last:
            last, still_since = state[1], time.monotonic()


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


async def stop_at_bot_check(ctx, page, tool: str) -> dict | None:
    """If the page shows a bot check, end the visit as blocked and return the tool's result; else None.

    Nothing is done about the check: not clicked, not waited out, not solved. The visit says it was
    blocked by a bot check and keeps a screenshot of what was shown.
    """
    found = await bot_check.detect(page)
    if found is None:
        return None
    ctx.entry["bot_check"] = {**found, "step": ctx.tool_calls}
    ctx.finished = {"outcome": "blocked", "stopped_by": "bot_check", "reason": bot_check.reason(found)}
    result = {
        "success": False, "changed": False, "kind": tool, "reason": "bot_check", "url": found["url"],
        "bot_check": True,
        "message": "The site is showing a bot check. The visit does not try to get past it, and is ending as "
                   "blocked by a bot check.",
    }
    try:
        image = await page.screenshot(type="png")
        if url := await publish_image(ctx, image, tool, "png"):
            result["screenshot_url"] = url
    except Exception:
        pass
    return result


@neatlogs.span(kind="TOOL", tool_name="look")
@lookups_nest_here
@metered
async def look() -> dict:
    ctx = current_run.get()
    page = await _active_page()
    if (stopped := await stop_at_bot_check(ctx, page, "look")) is not None:
        return {**stopped, "title": await page.title(), "unchanged": False, "summary": "", "interactive": []}
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
    # The brain sees this screenshot as an image next to the result (browse.py), so it can
    # judge visual state such as colours; it is not part of the span output.
    try:
        # Taken with any test login hidden in the page, so the screenshot cannot show it.
        async with credentials_module.redacted_page(page):
            image = await page.screenshot(type="png")  # PNG: the screenshots bucket accepts no JPEG
    except Exception:
        image = None
    if image is not None:
        ctx.pending_image = base64.b64encode(image).decode()
        result["screenshot_attached"] = True
        if url := await publish_image(ctx, image, "look", "png"):
            # The exported trace shows this URL in place of the inline image (trace_media.py).
            trace_media.register_url(ctx.pending_image, url)
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
    For typing, the same click focuses the field and the text is typed on the keyboard.
    """
    page = await _active_page()
    words = []
    if any(word in instruction.lower() for word in _TOGGLE_WORDS):
        words = [w for w in re.findall(r"[a-z0-9]+", instruction.lower()) if len(w) >= 3 and w not in _STOP_WORDS]
    typing = bool(action and action["method"] in ("fill", "type") and action["arguments"])
    clicking = bool(action and action["method"] in ("click", "check", "uncheck"))
    selector = action["selector"] if typing or clicking else None
    if selector is None and not words:
        return {"reported_success": False, "via": "no element to click"}
    target = await page.evaluate(_MOUSE_TARGET_JS.replace("%s", json.dumps({"selector": selector, "words": words})))
    if not target:
        return {"reported_success": False, "via": "no element to click"}
    await page.click(target["x"], target["y"])
    if typing:
        await page.type(action["arguments"][0])
        return {"reported_success": True, "via": "mouse.click+keyboard.type", "target": target["how"]}
    return {"reported_success": True, "via": "mouse.click", "target": target["how"], "toggle": target["toggle"]}


# "Click the search box" with nothing to type: typing focuses the field itself, so there is
# nothing to do, and no visible change is not a failure.
_FIELD_CLICK = re.compile(
    r"^\s*(click|tap|focus|go to|move to)\b.*\b(text ?box|field|input|search (box|bar)|text ?area)\b",
    re.IGNORECASE,
)
FOCUS_MESSAGE = (
    "Nothing to do: you do not need to click a text field before typing. Use do(\"type '<text>' into the "
    "<field name>\") and the field is focused for you."
)

# Errors that mean a script has not finished loading yet, rather than a broken site.
_NOT_LOADED = re.compile(
    r"is not defined|ChunkLoadError|Loading chunk|dynamically imported module|Failed to fetch dynamically",
    re.IGNORECASE,
)
READY_WAIT_MS = 15000

# Reads back the field that was typed into: the focused field, else the observed element.
_READ_FIELD_JS = r"""((spec) => {
  const byXpath = (xpath) => document.evaluate(
    xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  const find = (selector) => selector.startsWith('xpath=') ? byXpath(selector.slice(6))
    : selector.startsWith('/') ? byXpath(selector) : document.querySelector(selector);
  const isField = (el) => el && el.matches && el.matches(
    'input:not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]):not([type=hidden]),' +
    ' textarea, [contenteditable=""], [contenteditable=true]');
  let el = document.activeElement;
  if (!isField(el) && spec.selector) el = find(spec.selector);
  if (!isField(el)) return null;
  const value = el.isContentEditable ? el.innerText : (el.value || '');
  const label = ((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label')
    || el.placeholder || el.name || el.id || el.tagName.toLowerCase()).trim().slice(0, 60);
  return {
    label,
    value: el.type === 'password' ? '(hidden, ' + value.length + ' characters)' : value.slice(0, 200),
    contains_typed_text: spec.expected ? value.includes(spec.expected) : null,
  };
})(%s)"""
_QUOTED = re.compile(r"""['"\u2018\u201c]([^'"\u2019\u201d]+)['"\u2019\u201d]""")
_SUBMITS = re.compile(r"\b(press|enter key|submit|hit enter)\b", re.IGNORECASE)


async def _ladder(instruction: str, before: str, with_focus: bool) -> tuple[str | None, list[dict], dict | None]:
    """Run rungs a to d until one changes the page; return (rung that worked, rungs, observed action)."""
    rungs: list[dict] = []
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
        if not outcome["changed"]:
            # One more look before climbing: never click again on a page that has already moved.
            await asyncio.sleep(RECHECK_WAIT_S)
            outcome["changed"] = await _changed_since(before, with_focus, window=0)
            if outcome["changed"]:
                outcome["late"] = True
        rungs.append({"rung": name, **outcome})
        if outcome["changed"]:
            return name, rungs, action
    return None, rungs, action


async def _element_snapshot(page, mode: str) -> list[dict] | None:
    """The interactive elements' state ("before" picks them, "after" re-reads the same ones), or None."""
    try:
        return await page.evaluate(
            element_state.SNAPSHOT_JS % (element_state.MAX_ELEMENTS, element_state.MAX_LABEL, json.dumps(mode)))
    except Exception:
        return None


async def _wait_until_loaded(page) -> None:
    """Give a page whose scripts are still loading up to READY_WAIT_MS to finish."""
    for _ in range(READY_WAIT_MS // 500):
        if await page.evaluate("document.readyState") == "complete":
            break
        await page.wait_for_timeout(500)
    await page.wait_for_timeout(1000)


def _typed_text(instruction: str, action: dict | None) -> str | None:
    """The text a typing action put (or was told to put) into a field, if it can be told."""
    if action and action["method"] in ("fill", "type") and action["arguments"]:
        return action["arguments"][0]
    if match := _QUOTED.search(instruction):
        return match.group(1)
    return None


_PASSWORD_VISIBLE_JS = r"""[...document.querySelectorAll('input[type=password]')].some((el) => {
  const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none';
})"""


async def _password_visible(page) -> bool:
    try:
        return bool(await page.evaluate(_PASSWORD_VISIBLE_JS))
    except Exception:
        return False


async def _note_page_login(ctx, page, typed: str | None) -> None:
    """A password was typed with do(): was it a login written on the page itself, for visitors?

    "shown_on_page" when the typed text is in the page's visible text (a demo login), else "typed".
    The text is the agent's own, from what it read on the page; the test login is never typed with do().
    """
    if ctx.entry["page_login"] == "shown_on_page":
        return
    shown = False
    if typed and len(typed) >= 3:
        try:
            shown = bool(await page.evaluate(
                "document.body ? document.body.innerText.includes(" + json.dumps(typed) + ") : false"))
        except Exception:
            shown = False
    ctx.entry["page_login"] = "shown_on_page" if shown else "typed"


async def _read_back(page, instruction: str, action: dict | None) -> dict | None:
    """The typed-into field's label and actual value, and whether it contains the typed text."""
    expected = _typed_text(instruction, action)
    try:
        return await page.evaluate(_READ_FIELD_JS.replace("%s", json.dumps(
            {"selector": action["selector"] if action else None, "expected": expected})))
    except Exception:
        return None


@neatlogs.span(kind="TOOL", tool_name="do")
@metered
async def do(instruction: str) -> dict:
    ctx = current_run.get()
    page = await _active_page()
    if credentials_module.is_third_party_login(instruction):
        return {
            "success": False,
            "changed": False,
            "rung": "none",
            "via": "none",
            "reason": "third_party_login_not_allowed",
            "kind": "action",
            "url": await page.url(),
            "page_error_count": 0,
            "page_errors": [],
            "message": (
                "Not done: the visitor never uses Google, GitHub or any other third-party login. Use the "
                "email-and-password form with sign_in or sign_up, or call finish with outcome blocked and name "
                "the options the page offered."
            ),
        }
    typing = bool(_TYPING.search(instruction))
    if not typing and _FIELD_CLICK.search(instruction) and not _QUOTED.search(instruction):
        return {
            "success": True,
            "changed": False,
            "rung": "none",
            "via": "none",
            "reason": "focus_not_needed",
            "kind": "action",
            "url": await page.url(),
            "page_error_count": 0,
            "page_errors": [],
            "message": FOCUS_MESSAGE,
        }

    if (stopped := await stop_at_bot_check(ctx, page, "do")) is not None:
        return {**stopped, "rung": "none", "via": "none", "page_error_count": 0, "page_errors": []}

    with_focus = not typing
    retried_after_wait = False
    # The interactive elements' state just before the action, so a visual change is evidence.
    elements_before = None if typing else await _element_snapshot(page, "before")
    # Once a login written on the page has been typed, watch for the action that gets past it.
    watching_login = ctx.entry["page_login"] != "not_used" and not ctx.entry["page_login_worked"]
    login_before = (await _password_visible(page), await page.url()) if watching_login else None
    while True:
        page = await _active_page()
        before = await page_fingerprint(page, with_focus)
        since = await page_watch.now(page)
        worked, rungs, action = await _ladder(instruction, before, with_focus)
        settled_late = False
        if worked is None and await _changed_since(before, with_focus, window=FINAL_CHECK_WINDOW_S):
            # Nothing was seen during the ladder, but the page has moved since the action began:
            # a slow change. The attempt worked, on the rung that was running; record no issue.
            ran = [r["rung"] for r in rungs if "skipped" not in r]
            worked = ran[-1] if ran else "a"
            settled_late = True
        page = await _active_page()
        page_errors = await page_watch.collect(page, since)
        if worked or retried_after_wait or not any(_NOT_LOADED.search(e) for e in page_errors):
            break
        # The page's own scripts had not loaded yet: wait for them, then try once more. If some failed to
        # load at all, reload the page first, as a person would.
        print(f"[step {ctx.tool_calls}]   .. page scripts not loaded yet ({page_errors[0]}); waiting and retrying",
              flush=True)
        await _wait_until_loaded(page)
        if await page_watch.failed_assets(page):
            from visit import reload_if_broken

            await reload_if_broken(page, ctx.egress, ctx)
        retried_after_wait = True

    url = await page.url()
    element = None
    if elements_before:
        element = element_state.describe_change(
            instruction, elements_before, await _element_snapshot(page, "after"))
    broken_assets = [] if worked else await page_watch.failed_assets(page)
    if (login_before and worked and login_before[0] and url != login_before[1]
            and not await _password_visible(page)):
        ctx.entry["page_login_worked"] = True
        ctx.entry["login_wall_seen"] = False
    field = await _read_back(page, instruction, action) if typing else None
    if typing and field and str(field.get("value", "")).startswith("(hidden,"):
        await _note_page_login(ctx, page, _typed_text(instruction, action))
    screenshot_url = await _screenshot(ctx, page)

    # Every do() result has the same keys in the same order, with fixed values, so traces
    # can be searched with exact strings such as "changed": false or "kind": "agent_issue".
    if worked:
        result = {
            "success": True,
            "changed": True,
            "rung": worked,
            "via": VIA[worked] if worked in VIA else rungs[-1].get("via", "locator"),
            "reason": "worked_first_try" if worked == "a" and not retried_after_wait else "worked_after_retry",
            "kind": "action",
            "url": url,
            "page_error_count": len(page_errors),
            "page_errors": page_errors,
            "message": "The action worked." if worked == "a" and not retried_after_wait else RETRY_MESSAGE,
        }
    elif page_errors or broken_assets:
        # Nothing changed, and the page itself reported errors or failed requests while we
        # tried, or its own scripts never loaded: that points at the site, so it is site
        # friction, not our tool's issue.
        if page_errors:
            happened = "Nothing on the page changed, and the page reported errors: " + "; ".join(page_errors)
            detected_by = "page_errors"
        else:
            happened = ("Nothing on the page changed, because the page's own files failed to load, even after "
                        f"reloading: {page_watch.describe_assets(broken_assets)}.")
            detected_by = "failed_assets"
            page_errors = [f"request: failed to load {a['url']}" for a in broken_assets[:3]]
        ctx.frictions.append({
            "kind": "site",
            "severity": "medium",
            "expected": f"'{instruction}' has a visible effect",
            "happened": happened,
            "url": url,
            "detected_by": detected_by,
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
    if retried_after_wait:
        result["retried_after_wait"] = True
    if element:
        result["element"] = element
    if settled_late:
        result["settled_late"] = True
    if typing:
        result["field"] = field
        if field and field.get("contains_typed_text") is False and not _SUBMITS.search(instruction):
            result["message"] += (
                f" Check the field: '{field['label']}' now reads '{field['value']}', which does not contain the "
                "text you typed. It may have gone into another field or been lost; look at the page before going on."
            )
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


async def publish_image(ctx: RunContext, image: bytes, prefix: str, extension: str) -> str | None:
    """Save an image in the run's folder and, when a database is configured, upload it."""
    ctx.screenshots += 1
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.run_dir / f"{prefix}_{ctx.screenshots}.{extension}"
    path.write_bytes(image)
    if ctx.recorder is None:
        return None
    try:
        return await ctx.recorder.upload_screenshot(path)
    except Exception as error:
        print(f"[step {ctx.tool_calls}]   !! could not upload {path.name}: {type(error).__name__}: {error}", flush=True)
        return None


async def _screenshot(ctx: RunContext, page) -> str | None:
    """Save a screenshot of the page and, when a database is configured, upload it.

    Returns the public URL, which neatlogs shows as an image preview on the tool span,
    or None for local runs and failed uploads.
    """
    ctx.screenshots += 1
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.run_dir / f"step_{ctx.screenshots}.png"
    try:
        # With any test login hidden in the page; if it cannot be hidden, no screenshot is saved.
        async with credentials_module.redacted_page(page):
            await page.screenshot(path=path)
    except Exception:
        return None
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
            "up to 15 things you could interact with, and a screenshot of the visible part of the page. "
            "If the page has not changed since your last look, it says so instead of repeating the result. "
            "Call this when the page may have changed."
        ),
        "input_schema": _schema({}, []),
        "strict": True,
    },
    {
        "name": "do",
        "description": (
            "Perform ONE single-step action on the page, such as clicking one button or typing text into one field. "
            "Typing focuses the field for you, so do not click a text field first. After typing, the result shows "
            "what the field actually contains. "
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
