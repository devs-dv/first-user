"""What happened after the visitor submitted a login or sign-up form.

A form that disappears is not proof of a login, and a form that stays is not always a rejection.
After sign_in or sign_up the result is decided here, from what the page shows and what its own
requests returned, into exactly one of:

  signed_in            the form is gone, no challenge appeared, no error is showing
  rejected             the page said no: its error message (quoted) and any 401, 403 or 429
  needs_verification   a step the visitor cannot do: a code sent by email, a CAPTCHA, or a
                       two-factor code
  no_effect            submitting changed nothing and the page said nothing

Pure functions on plain values, so they can be tested without a browser. The page_message and the
request lines come from the page and are scrubbed by the caller before they are shown.
"""

import re

RESULTS = ("signed_in", "rejected", "needs_verification", "no_effect")
CHALLENGES = ("email_verification", "captcha", "two_factor")

# An alert that is showing and says something went wrong, even when the form has been replaced.
NEGATIVE = re.compile(
    r"(invalid|incorrect|wrong|fail(ed|ure)?|error|not (found|recogni[sz]ed|correct|valid|match)|denied|"
    r"unauthori[sz]ed|forbidden|try again|does ?n[o']t match|locked|too many|already (exists|registered|in use|taken))",
    re.IGNORECASE,
)
# The statuses worth quoting: the page's own requests that said "not you" or "slow down".
STATUS = re.compile(r"\b(401|403|429)\b")

CHALLENGE_TEXT = {
    "email_verification": "a code or link sent by email",
    "captcha": "a CAPTCHA",
    "two_factor": "a two-factor code",
}
FORM_NAME = {"sign_in": "test login", "sign_up": "sign-up"}


def diagnose(*, stage: str, before: dict, after: dict, submitted: bool, errors: list[str],
             before_url: str, after_url: str, step: int | None = None, detail: str | None = None) -> dict:
    """The structured diagnosis of one submit. `before` and `after` are auth_tools._scan results."""
    message = " ".join((after.get("page_message") or "").split())[:200]
    request_lines = [line for line in errors if STATUS.search(line)][:3]
    statuses = list(dict.fromkeys(match for line in request_lines for match in STATUS.findall(line)))

    # A challenge counts only when it appeared because of the submit, not when it was already on the page.
    challenge = after.get("challenge") or ""
    if challenge and challenge == (before.get("challenge") or ""):
        challenge = ""
    form_visible = bool(after.get("has_password"))

    if detail is not None:
        result = "no_effect"  # the form could not even be filled in
    elif challenge:
        result = "needs_verification"
    elif form_visible or statuses or (message and NEGATIVE.search(message)):
        # Said no, in words or in a status; or the form is simply still there after something happened.
        result = "rejected" if (message or statuses or submitted) else "no_effect"
    elif not submitted and after_url == before_url:
        result = "no_effect"
    else:
        result = "signed_in"

    return {
        "stage": stage,
        "result": result,
        "challenge": challenge or None,
        "page_message": message or None,
        "http_statuses": statuses,
        "http_requests": request_lines,
        "form_still_visible": form_visible,
        "url": after_url,
        "step": step,
        **({"detail": detail} if detail else {}),
    }


def describe(diagnosis: dict) -> str:
    """The exact reason for a run that ends blocked here: what the page said and what it returned."""
    form = FORM_NAME.get(diagnosis["stage"], "form")
    result = diagnosis["result"]
    message = diagnosis.get("page_message")
    statuses = diagnosis.get("http_statuses") or []
    status_text = f" (the page's own request returned {' and '.join(statuses)})" if statuses else ""
    if result == "rejected":
        if message:
            return f'The page rejected the {form}: "{message}"{status_text}.'
        if statuses:
            return f"The page rejected the {form} without a message{status_text}."
        return f"The page rejected the {form}: the form was still showing afterwards and gave no message."
    if result == "needs_verification":
        needed = CHALLENGE_TEXT.get(diagnosis.get("challenge") or "", "a verification step")
        quoted = f' It said: "{message}".' if message else ""
        return (f"Getting in needs {needed}, which the visitor cannot do, so the visit stopped at the "
                f"{form}.{quoted}")
    if result == "no_effect":
        if diagnosis.get("detail"):
            return f"The {form} could not be completed: {diagnosis['detail']}"
        return f"Submitting the {form} had no effect: the page did not change and showed no message."
    return f"The {form} worked."


def evidence(diagnosis: dict) -> dict:
    """The part of a diagnosis kept as evidence on a blocked run."""
    return {key: diagnosis.get(key) for key in (
        "step", "url", "page_message", "http_statuses", "http_requests", "challenge", "form_still_visible")}
