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

import credentials
import element_state
import hidden_text
import trace_media
import trace_safety
from config import VERIFIER_MODEL

MAX_TEXT_CHARS = 6000
MAX_FIELDS = 40
VERDICTS = ("verified", "contradicted", "unverified")

SYSTEM_PROMPT = """\
You check whether a task on a website was completed. You get the task, a factual record of what was done in the browser, and the current state of the page. The record lists each action as it was instructed, whether the page changed after it (measured automatically by comparing the page before and after), the URL afterwards, and short descriptions of the page written at the time. It does not say whether the task succeeded; that is for you to judge.

For an action on an element, the record may also give that element's state just before and just after it (its text, class, ARIA state and computed colours, read from the page automatically). A difference between the two is a change that happened; no difference, or no entry, says nothing either way.

Return one of three verdicts. The difference between the last two matters most:

- verified: there is concrete evidence the task was completed. For a task that is a sequence of steps, the evidence can be the actions that changed the page in the record together with a final state consistent with them, for example three "Add" clicks that changed the page and a final page showing the expected result. A change recorded after the action plus a final state that matches what the task expects is enough; you do not need a before-picture.

- contradicted: ONLY when there is positive evidence that the task was NOT completed, and you can quote it. The evidence must be something that is PRESENT. Examples: an error message on the page or in the record; a final page showing the wrong result (wrong item, wrong value, a different page than the task needs); an action in the record that was tried and did not change the page, with nothing else changed.

- unverified: the evidence is incomplete or ambiguous, so you cannot tell either way. Examples: there is no before-state to compare against; intermediate steps cannot be seen; the final state is consistent with the task but could also have been there already; the record is thin. Something that is merely ABSENT is never contradicting evidence: an empty or short record, a click that is not in the record, a missing before-picture, a result that might already have been there. All of these are unverified. Missing evidence is never evidence of failure; when in doubt between contradicted and unverified, choose unverified.

Base the verdict only on the record and the page. Give a short reason that names the evidence. For contradicted, also quote the positive evidence of failure in contradicting_evidence; for the other verdicts leave it empty."""

VERDICT_TOOL = {
    "name": "verdict",
    "description": (
        "Report whether the task was completed. Use contradicted only with quoted positive evidence "
        "that it was not; use unverified when the evidence is merely incomplete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "reason": {"type": "string", "description": "One or two sentences naming the evidence."},
            "contradicting_evidence": {
                "type": "string",
                "description": (
                    "For contradicted only: the quoted error message, wrong result or failed step, which must be "
                    "present on the page or in the record, that shows the task was not completed. An absence "
                    "(an empty record, no recorded action) is not evidence. Empty for verified and unverified."
                ),
            },
        },
        "required": ["verdict", "reason", "contradicting_evidence"],
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


async def read_page(page, step: int | None = None, where: str = "final_check") -> dict:
    """A fresh read of the page, with no model call.

    Hidden text addressed to AI agents is removed from the page first (hidden_text.py), so neither the text nor
    the screenshot given to a model carries it; where it was found is recorded as evidence.

    Read with any test login hidden in the page (credentials.redacted_page), and scrubbed again,
    so neither the text, the field values nor the screenshot can carry it to a model.
    """
    await hidden_text.sweep(page, step, where)
    async with credentials.redacted_page(page):
        text = await page.evaluate("document.body ? document.body.innerText : ''") or ""
        fields = json.loads(await page.evaluate(_FIELDS_JS))
        screenshot = await page.screenshot(type="png")
    return {
        "url": trace_safety.scrub(await page.url()),
        "title": trace_safety.scrub(await page.title()),
        "text": trace_safety.scrub(text[:MAX_TEXT_CHARS]),
        "fields": trace_safety.scrub(fields),
        "screenshot": base64.b64encode(screenshot).decode(),
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
            if entry.get("field_after"):
                line += f"; field afterwards: {entry['field_after']}"
            if entry.get("element"):
                line += "; " + element_state.format_for_record(entry["element"])
            line += f"; URL after: {entry.get('url_after')}"
        lines.append(line)
    return "\n".join(lines) or (
        "(Nothing was recorded. This says nothing about whether the task was completed; judge from the final page.)"
    )


# capture_input=False: `page`, `usage` and `publish` are live objects, and neatlogs would walk
# their attributes. The input that matters is recorded explicitly below.
@neatlogs.span(kind="EVALUATOR", name="verify_goal", capture_input=False)
async def verify(goal: str, record: list[dict], page, usage=None, publish=None,
                 success_condition: str | None = None) -> dict:
    """Return {"verdict", "reason", "model", "url"}; adds the call's tokens to `usage`.

    `publish`, if given, uploads the screenshot (bytes) and returns its public URL, which the
    exported trace shows in place of the inline image (trace_media.py).
    """
    trace_safety.set_input(goal=goal, record=record, success_condition=success_condition)
    snapshot = await read_page(page)
    if publish is not None and (url := await publish(base64.b64decode(snapshot["screenshot"]))):
        trace_media.register_url(snapshot["screenshot"], url)
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
                    {"type": "text", "text": f"Task: {goal}" + (
                        f"\n\nSuccess condition given by the founder: {success_condition}\n"
                        "Judge whether THIS condition is met by what the record and the final page show; the "
                        "task wording alone is not enough." if success_condition else "")},
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
        verdict = {"verdict": "unverified", "reason": f"Unexpected verdict {verdict['verdict']!r}: {verdict['reason']}",
                   "contradicting_evidence": ""}
    result = {"verdict": verdict["verdict"], "reason": verdict["reason"], "model": VERIFIER_MODEL,
              "url": snapshot["url"]}
    if verdict["verdict"] == "contradicted":
        evidence = (verdict.get("contradicting_evidence") or "").strip()
        if evidence:
            result["contradicting_evidence"] = evidence
        else:
            # "Contradicted" needs quoted positive evidence; without it the evidence is only incomplete.
            result["verdict"] = "unverified"
            result["reason"] = "No positive evidence of failure was given. " + result["reason"]
            result["downgraded_from"] = "contradicted"
    return result
