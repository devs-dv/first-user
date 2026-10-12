"""Which eval cases exist, and how a live run becomes one. Pure: no database, no tracing, so it can be tested.

  sites.json        the hand-checked set (known sites, goals verified by hand)
  real_world.json   cases turned from live runs with evals/from_run.py

Nothing secret is ever copied from a run: no test login, no address with a user name or password in it, no
address whose query holds a token or key, no goal that a secret-shaped string appears in.
"""

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parent
FILES = {"sites": "sites.json", "real_world": "real_world.json"}
EXPECTATIONS = ("achieved", "broken")
ACCESS_MODES = ("public", "link", "account", "signup")
SECRET_QUERY_NAME = re.compile(r"(token|key|secret|passw|auth|sig|session|jwt|bearer|code|otp|credential)", re.I)


class NotSafeToCopy(Exception):
    """Part of the run looks like a secret, so it is not copied into a case file."""


def load_cases(only: list[str] | None = None, which: str = "sites", root: Path = ROOT) -> list[dict]:
    """The cases of "sites", "real_world" or "all". A missing real_world.json is an empty list."""
    names = list(FILES) if which == "all" else [which]
    cases: list[dict] = []
    for name in names:
        path = root / FILES[name]
        if not path.exists():
            if name == "sites":
                raise FileNotFoundError(path)
            continue
        cases += json.loads(path.read_text(encoding="utf-8"))["cases"]
    return [resolve_url(case) for case in cases if not only or case["id"] in only]


def resolve_url(case: dict) -> dict:
    """A case with "url_env" (the name of an environment variable holding a base address, such as
    DEMO_SHOP_URL) gets its "url" from that base plus its "url_path". With the variable unset or not
    an http(s) address, "url" stays None and runnable() says why. Other cases are returned as they are."""
    name = case.get("url_env")
    if not name:
        return case
    base = (os.environ.get(name) or "").strip().rstrip("/")
    if not re.match(r"^https?://[^/\s]+$", base):
        return {**case, "url": None}
    path = case.get("url_path") or "/"
    return {**case, "url": base + (path if path.startswith("/") else "/" + path)}


def runnable(case: dict) -> tuple[bool, str]:
    """Can this case be queued as it is? A case from a run that needed a test login cannot: the login is
    never stored, so it would only show the visitor stuck at the login."""
    if case.get("url_env") and not case.get("url"):
        return False, f"{case['url_env']} is not set to the deployed site's address (https://host, no path)"
    if case.get("needs_test_login"):
        return False, "needs a test login, which is never stored"
    if case.get("needs_start_link"):
        return False, "needs a start link that held a secret and was not stored"
    return True, ""


def clean_url(url: str | None) -> str | None:
    """The address if it is safe to keep, None if there is none, NotSafeToCopy if it carries a secret."""
    if not url:
        return None
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise NotSafeToCopy("an address has a user name or password in it")
    for name, _ in parse_qsl(parts.query, keep_blank_values=True):
        if SECRET_QUERY_NAME.search(name):
            raise NotSafeToCopy(f"an address has a '{name}' parameter, which may be a secret")
    return url


def case_from_run(row: dict, expect: str, note: str, today: date | None = None) -> dict:
    """A case file entry from a run row. `row` needs id, url, goal and may have access_mode, start_url,
    success_condition and has_test_login. Raises ValueError for a bad expectation, NotSafeToCopy for a secret."""
    import trace_safety  # worker/ is on the path for callers

    if expect not in EXPECTATIONS:
        raise ValueError(f"--expect must be one of {', '.join(EXPECTATIONS)}")
    if not note.strip():
        raise ValueError("--note is required: say what a person would see, or what is wrong")
    for label, text in (("goal", row.get("goal")), ("success condition", row.get("success_condition")),
                        ("note", note)):
        if text and trace_safety.redact_text(str(text)) != str(text):
            raise NotSafeToCopy(f"the {label} contains something that looks like a secret")

    mode = row.get("access_mode") if row.get("access_mode") in ACCESS_MODES else None
    try:
        start_url = clean_url(row.get("start_url"))
    except NotSafeToCopy:
        start_url = None  # a demo link with a token in it is not kept; the case says it needs one
    case = {
        "id": f"real_{str(row['id'])[:8]}",
        "kind": "achievable" if expect == "achieved" else "broken",
        "url": clean_url(row["url"]),
        "goal": row["goal"],
        "access_mode": mode,
        "start_url": start_url,
        "success_condition": row.get("success_condition") or None,
        "expected_outcome": expect,
        "note": note.strip(),
        "source_run_id": str(row["id"]),
        "added": (today or date.today()).isoformat(),
    }
    if expect == "broken":
        case["known_issue"] = note.strip()  # what the eval's judge looks for in the run's report
    # The login itself is never stored; the case only says that it needs one.
    if row.get("has_test_login") or mode == "account":
        case["needs_test_login"] = True
    if row.get("start_url") and start_url is None:
        case["needs_start_link"] = True
    return case


def merge_case(document: dict | None, case: dict) -> dict:
    """The case file with `case` added, or replacing an earlier case from the same run."""
    document = document or {"description": "Cases turned from live runs with evals/from_run.py.", "cases": []}
    cases = [c for c in document["cases"] if c.get("source_run_id") != case["source_run_id"]]
    cases.append(case)
    return {**document, "cases": cases}
