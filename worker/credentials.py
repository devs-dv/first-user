"""A run's test login and generated test identity, and keeping them out of everything.

Where the values may go: into the page being tested, typed by sign_in / sign_up, and nowhere
else. They are not passed to a model, a step, a result, a log line or a span:

  * TestCredentials has no __dict__ and a hidden repr, so a serializer that walks an object's
    attributes (neatlogs does) finds nothing, and printing it shows nothing.
  * Registered values are replaced by labels ("[test email]", "[test password]") in everything
    that goes toward a model, a step record or a result (trace_safety.scrub), and in every
    exported span (trace_safety.mask).
  * redacted_page() swaps the values for labels inside the page for the moment a screenshot or
    a text read is taken, so neither shows them, then puts them back.
"""

import json
import re
import secrets
import string
from contextlib import asynccontextmanager

import trace_safety

EMAIL_LABEL = "[test email]"
PASSWORD_LABEL = "[test password]"
GENERATED_EMAIL_DOMAIN = "example.com"  # reserved for documentation: nothing is delivered there


_THIRD_PARTY = re.compile(
    r"\b(google|github|gitlab|facebook|apple|microsoft|linkedin|twitter|okta|slack|discord|sso|single sign[- ]on)\b",
    re.IGNORECASE,
)
_LOGIN_ACTION = re.compile(
    r"\b(sign ?in|sign ?up|log ?in|login|register|continue|connect|authenticate)\b", re.IGNORECASE
)


def is_third_party_login(instruction: str) -> bool:
    """True for an instruction to use Google, GitHub or another third-party login."""
    return bool(_THIRD_PARTY.search(instruction) and _LOGIN_ACTION.search(instruction))


class TestCredentials:
    """An email and a password. Never printed, never serialised: read .email / .password to type."""

    __slots__ = ("_email", "_password")
    __test__ = False  # not a test class, despite the name

    def __init__(self, email: str, password: str):
        self._email = email
        self._password = password

    @property
    def email(self) -> str:
        return self._email

    @property
    def password(self) -> str:
        return self._password

    def register(self, include_email: bool = True) -> None:
        """Start redacting these values everywhere (see module docstring).

        A generated identity's email is not registered: it is shown to the founder on purpose, so
        they can find and delete the test account. Only its password is secret.
        """
        if include_email:
            trace_safety.register_secret(self._email, EMAIL_LABEL)
        trace_safety.register_secret(self._password, PASSWORD_LABEL)

    def __repr__(self) -> str:
        return "TestCredentials(<hidden>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("TestCredentials cannot be pickled or copied")


class TestIdentity:
    """A generated identity for self sign-up: a name, an email and a random password."""

    __slots__ = ("first_name", "last_name", "credentials")
    __test__ = False

    def __init__(self, first_name: str, last_name: str, credentials: TestCredentials):
        self.first_name = first_name
        self.last_name = last_name
        self.credentials = credentials

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def email(self) -> str:
        return self.credentials.email

    def __repr__(self) -> str:
        return f"TestIdentity({self.full_name!r}, <hidden>)"

    __str__ = __repr__


def generate_identity() -> TestIdentity:
    """A throwaway identity: First User + a random address and a strong random password."""
    tag = secrets.token_hex(4)
    letters = string.ascii_letters + string.digits
    body = "".join(secrets.choice(letters) for _ in range(12))
    # One of each class, so a strict password policy accepts it; shuffled so the order is not fixed.
    chars = list(body + secrets.choice(string.ascii_uppercase) + secrets.choice(string.ascii_lowercase)
                 + secrets.choice(string.digits) + secrets.choice("!#$%&*?"))
    secrets.SystemRandom().shuffle(chars)
    credentials = TestCredentials(f"first.user.{tag}@{GENERATED_EMAIL_DOMAIN}", "".join(chars))
    return TestIdentity("First", "User", credentials)


# No secret is ever sent into a page. A page under test is not trusted: it may be another
# company's site, or a third party the visit was redirected to, and script in the page can hook
# built-ins to watch anything a script we run there handles. So the swap works the other way
# round:
#   1. _COLLECT_JS returns the page's own text nodes and field values (data the page already has)
#      and keeps references to the nodes;
#   2. Python finds, with the secrets, which of them show one, and works out their replacements;
#   3. _APPLY_JS receives only node indexes and the replacement strings (which hold labels);
#   4. _RESTORE_JS puts every original back.
# Shadow DOM and iframes are not reached.
_MAX_NODES = 20000
_MIN_NODE_CHARS = 4
_COLLECT_JS = r"""(() => {
  const texts = [];
  window.__firstUserNodes = [];
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node && texts.length < %d; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (parent && /^(SCRIPT|STYLE|NOSCRIPT)$/.test(parent.tagName)) continue;
    if (node.nodeValue && node.nodeValue.length >= %d) { window.__firstUserNodes.push(node); texts.push(node.nodeValue); }
  }
  window.__firstUserFields = [...document.querySelectorAll('input, textarea')].filter((el) => el.value && el.value.length >= %d);
  return JSON.stringify({texts, values: window.__firstUserFields.map((el) => el.value)});
})()""" % (_MAX_NODES, _MIN_NODE_CHARS, _MIN_NODE_CHARS)

_APPLY_JS = r"""((textChanges, valueChanges) => {
  const undo = [];
  for (const [index, replacement] of textChanges) {
    const node = window.__firstUserNodes[index];
    if (node && node.isConnected) { const original = node.nodeValue; undo.push(() => { node.nodeValue = original; }); node.nodeValue = replacement; }
  }
  for (const [index, replacement] of valueChanges) {
    const el = window.__firstUserFields[index];
    if (el) { const original = el.value; undo.push(() => { el.value = original; }); el.value = replacement; }
  }
  window.__firstUserRestore = () => {
    undo.forEach((f) => f());
    delete window.__firstUserRestore; delete window.__firstUserNodes; delete window.__firstUserFields;
  };
  return undo.length;
})(%s, %s)"""
_RESTORE_JS = (
    "window.__firstUserRestore ? window.__firstUserRestore() : "
    "(delete window.__firstUserNodes, delete window.__firstUserFields, 0)"
)


@asynccontextmanager
async def redacted_page(page):
    """While active, registered secrets shown in the page are replaced by labels.

    Wrap a screenshot or a text read in it; the page is put back afterwards, also on error.
    No secret is sent into the page: see the comment above _COLLECT_JS.
    """
    if not trace_safety._registered:
        yield
        return
    swapped = False
    try:
        try:
            collected = json.loads(await page.evaluate(_COLLECT_JS))
            text_changes = [[i, scrubbed] for i, text in enumerate(collected["texts"])
                            if (scrubbed := trace_safety.scrub_text(text)) != text]
            value_changes = [[i, scrubbed] for i, value in enumerate(collected["values"])
                             if (scrubbed := trace_safety.scrub_text(value)) != value]
            if text_changes or value_changes:
                await page.evaluate(_APPLY_JS.replace("%s", json.dumps(text_changes), 1)
                                    .replace("%s", json.dumps(value_changes), 1))
                swapped = True
        except Exception:
            # Could not swap: better no screenshot than one that shows a secret.
            raise RuntimeError("could not hide the test login in the page before capturing it") from None
        yield
    finally:
        try:
            await page.evaluate(_RESTORE_JS)
        except Exception:
            pass
