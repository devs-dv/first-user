"""Independent check of an "achieved" verdict.

The verifier never sees the agent's thoughts, notes or finish reason. It gets the goal,
the factual record of the run (each action's instruction, whether the page changed, the
URL afterwards, and the page summaries from look()), and a fresh read of the final page
(URL, title, visible text, form state and a screenshot). It returns one of three verdicts:

  verified      concrete evidence that the goal was met
  contradicted  evidence that it was not met
  unverified    not enough evidence either way
"""

import base64
import json

import neatlogs
from anthropic import AsyncAnthropic

from config import VERIFIER_MODEL

MAX_TEXT_CHARS = 6000
MAX_FIELDS = 40
VERDICTS = ("verified", "contradicted", "unverified")

SYSTEM_PROMPT = """\
You check whether a task on a website was completed. You get the task, a factual record of what was done in the browser, and the current state of the page. The record lists each action as it was instructed, whether the page changed after it (measured automatically by comparing the page before and after), the URL afterwards, and short descriptions of the page written at the time. It does not say whether the task succeeded; that is for you to judge.

Return one verdict:
- verified: there is concrete evidence the task was completed. For a task that is a sequence of steps, the evidence can be the actions that changed the page in the record together with a final state consistent with them, for example three "Add" clicks that changed the page and a final page showing the expected result.
- contradicted: there is evidence the task was not completed, for example the final page shows an error or the wrong result, the expected item is missing, or a step the task needs never changed the page.
- unverified: neither of the above; the evidence is too thin or ambiguous to decide.

Base the verdict only on the record and the page. Give a short reason that names the evidence."""

VERDICT_TOOL = {
    "name": "verdict",
    "description": "Report whether the task was completed, with a short reason naming the evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "reason": {"type": "string", "description": "One or two sentences naming the evidence."},
        },
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    },
}

# Field values for the verifier: passwords are never included.
_FIELDS_JS = r"""JSON.stringify(Array.from(document.querySelectorAll('input, textarea, select'))
  .filter((el) => el.type !== 'hidden')
  .slice(0, %d)
  .map((el) => {
    const label = (el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label')
      || el.placeholder || el.name || el.id || el.type;
    const value = el.type === 'password' ? '(password)'
      : (el.type === 'checkbox' || el.type === 'radio') ? (el.checked ? 'checked' : 'not checked') : el.value;
    return label.trim().slice(0, 60) + ': ' + String(value).slice(0, 80);
  }))""" % MAX_FIELDS


async def read_page(page) -> dict:
    """A fresh read of the page, with no model call."""
    text = await page.evaluate("document.body ? document.body.innerText : ''") or ""
    return {
        "url": await page.url(),
        "title": await page.title(),
        "text": text[:MAX_TEXT_CHARS],
        "fields": json.loads(await page.evaluate(_FIELDS_JS)),
        "screenshot": base64.b64encode(await page.screenshot(type="png")).decode(),
    }


def format_record(record: list[dict]) -> str:
    lines = []
    for entry in record:
        if entry["tool"] == "look":
            line = f"{entry['step']}. look at {entry.get('url')}: {entry.get('summary', '')}"
            if entry.get("interactive"):
                line += " Interactive items: " + "; ".join(entry["interactive"])
        elif entry["tool"] == "do":
            line = f"{entry['step']}. do \"{entry['instruction']}\""
        else:
            line = f"{entry['step']}. {entry['tool']}" + (f" {entry['direction']}" if entry.get("direction") else "")
        if "error" in entry:
            line += f" -> tool error: {entry['error']}"
        elif entry["tool"] != "look":
            if "page_changed" in entry:
                line += " -> page changed" if entry["page_changed"] else " -> page did NOT change"
            if entry.get("page_errors"):
                line += f"; the page reported errors: {'; '.join(entry['page_errors'])}"
            line += f"; URL after: {entry.get('url_after')}"
        lines.append(line)
    return "\n".join(lines) or "(no actions)"


@neatlogs.span(kind="EVALUATOR", name="verify_goal")
async def verify(goal: str, record: list[dict], page, usage=None) -> dict:
    """Return {"verdict", "reason", "model", "url"}; adds the call's tokens to `usage`."""
    snapshot = await read_page(page)
    fields = "\n".join(snapshot["fields"]) or "(none)"
    client = neatlogs.wrap(AsyncAnthropic())
    try:
        response = await client.messages.create(
            model=VERIFIER_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[VERDICT_TOOL],
            tool_choice={"type": "tool", "name": "verdict"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Task: {goal}"},
                    {"type": "text", "text": f"Record of what was done:\n{format_record(record)}"},
                    {"type": "text", "text": (
                        f"Final page now:\nURL: {snapshot['url']}\nTitle: {snapshot['title']}\n\n"
                        f"Form fields:\n{fields}\n\nVisible text:\n{snapshot['text']}"
                    )},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": snapshot["screenshot"]}},
                ],
            }],
        )
    finally:
        await client.close()
    if usage is not None:
        usage.add_verifier_response(response)
    verdict = next(block.input for block in response.content if block.type == "tool_use")
    if verdict["verdict"] not in VERDICTS:
        verdict = {"verdict": "unverified", "reason": f"Unexpected verdict {verdict['verdict']!r}: {verdict['reason']}"}
    return {"verdict": verdict["verdict"], "reason": verdict["reason"], "model": VERIFIER_MODEL,
            "url": snapshot["url"]}
