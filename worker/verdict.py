"""One verdict per run: can a first-time visitor get value from this site?

Computed in code from the outcome, the independent check and our own-issue count, so it does not
depend on what the model wrote. Stored on the run result as

    {kind, headline, where_step, where_url, evidence_quote, basis, ...}

Kinds, in the order they are decided:

  bot_check    stopped by a "verify you are human" check. Nothing is said about the site.
  our_failure  the run failed on our side (an error, a refusal, our browser tool having no effect with no
               sign of a site problem). Nothing is said about the site.
  login_wall   stopped at a login or sign-up it could not pass; carries the ways in.
  got_through  achieved, and the independent check confirmed it.
  unconfirmed  achieved, but the check could not confirm it; says what it could not see.
  stuck        blocked, gave up, ran out of steps, or the check contradicted the claim; names the page.

`basis` is "verified" only when the independent check backs the verdict (got_through, or a
contradicted claim); otherwise "observed".
"""

import re
from urllib.parse import urlsplit

KINDS = ("got_through", "unconfirmed", "stuck", "login_wall", "bot_check", "our_failure")
NO_SITE_FINDINGS = ("our_failure", "bot_check")

WAYS_IN = (
    "Give a demo or guest link: a page that is already past the login, where the visit begins.",
    "Give a throwaway test account: an email and password for an account with no real data.",
    "Let the visitor sign up by itself: this works for an email-and-password signup without email verification.",
)

# Stops that are our limit or our error, not something the site did.
OUR_STOPS = ("api_error", "refusal", "max_tokens", "exception")


def page_label(url: str | None) -> str:
    """A short name for a page: its path, or the site's name for the front page."""
    if not url:
        return "the first page"
    parts = urlsplit(url)
    path = (parts.path or "/").rstrip("/")
    return f"{parts.netloc}{path}" if path else parts.netloc or url


def _clip(text: str | None, limit: int = 400) -> str:
    return " ".join(str(text or "").split())[:limit]


def compute_verdict(*, outcome: str, stopped_by: str | None, reason: str, verification: dict | None,
                    entry: dict, own_issue_steps: list[int], site_friction_count: int, page_error_count: int,
                    last_step: int | None, last_step_url: str | None,
                    site_evidence: tuple[int | None, str] | None = None) -> dict:
    """The run's verdict. `site_evidence` is (step, quote) of the site's own evidence if there is any."""
    verification = verification or {}
    where_step, where_url = last_step, last_step_url
    own_only = bool(own_issue_steps) and site_friction_count == 0 and page_error_count == 0

    if stopped_by == "bot_check" or entry.get("bot_check"):
        found = entry.get("bot_check") or {}
        return {
            "kind": "bot_check", "basis": "observed",
            "headline": "The site blocked the visit with a bot check",
            "where_step": found.get("step") or where_step, "where_url": found.get("url") or where_url,
            "evidence_quote": _clip(found.get("phrase") or reason),
            "detail": "The visitor does not try to get past a bot check, so nothing is said about the site "
                      "behind it.",
        }

    if outcome == "error" or stopped_by in OUR_STOPS or (
        outcome in ("blocked", "gave_up", "max_steps") and own_only
        and last_step is not None and own_issue_steps and max(own_issue_steps) >= last_step - 1
    ):
        return {
            "kind": "our_failure", "basis": "observed",
            "headline": "The visit failed on our side, so this says nothing about your site",
            "where_step": own_issue_steps[-1] if own_issue_steps else where_step, "where_url": where_url,
            "evidence_quote": _clip(reason),
            "detail": "Our browser tool or an error stopped the visit, and the site gave no sign of a problem. "
                      "Run it again.",
        }

    if outcome == "blocked" and entry.get("blocked_at_login"):
        diagnosis = entry.get("diagnosis") or {}
        step = diagnosis.get("step") or where_step
        return {
            "kind": "login_wall", "basis": "observed",
            "headline": "A first-time visitor was stopped at a login",
            "where_step": step, "where_url": diagnosis.get("url") or where_url,
            "evidence_quote": _clip(diagnosis.get("page_message") or reason),
            "ways_in": list(WAYS_IN),
        }

    if outcome == "achieved" and verification.get("verdict") == "verified":
        return {
            "kind": "got_through", "basis": "verified",
            "headline": "A first-time visitor got through",
            "where_step": where_step, "where_url": where_url,
            "evidence_quote": _clip(verification.get("reason") or reason),
        }

    if outcome in ("achieved_unconfirmed", "unverified") or (
            outcome == "achieved" and verification.get("verdict") != "verified"):
        return {
            "kind": "unconfirmed", "basis": "observed",
            "headline": "The visitor says it got through, but we could not confirm it",
            "where_step": where_step, "where_url": where_url,
            "evidence_quote": _clip(verification.get("reason") or "The independent check did not run."),
            "detail": "What the independent check could not see: "
                      + (_clip(verification.get("reason")) or "it had no record to check."),
        }

    # blocked, gave_up, max_steps, or a claim the independent check contradicted
    contradicted = outcome == "not_achieved" or verification.get("verdict") == "contradicted"
    if site_evidence and site_evidence[0] is not None:
        where_step = site_evidence[0]
    quote = (verification.get("contradicting_evidence") if contradicted else None) or \
        (site_evidence[1] if site_evidence else None) or reason
    return {
        "kind": "stuck", "basis": "verified" if contradicted else "observed",
        "headline": f"A first-time visitor got stuck on {page_label(where_url)}",
        "where_step": where_step, "where_url": where_url,
        "evidence_quote": _clip(quote),
        **({"detail": "The independent check found the goal was not met."} if contradicted else {}),
    }


def has_unpromised_basis(verdict: dict) -> bool:
    return verdict.get("kind") in KINDS and verdict.get("basis") in ("observed", "verified")
