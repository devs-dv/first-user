"""Run the real worker path against a local site with a login, and report where credentials went.

Used by test_credentials.py; it can also be run by hand:

    python credentials_harness.py REPORT.json [scenario ...]

For each scenario it serves a small local site, runs worker_run.execute() (the real visit: a real
browser, the real model, the real tools) with a stand-in database, and records everything that
leaves the process: what the database would be given, every step record, every exported span
(after the neatlogs mask), the text of every model request, and what the page showed when
screenshots were taken. The test then searches all of it for the credentials. A real model is
used, so a run costs a few cents.
"""

import asyncio
import json
import os
import re
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
os.environ["BRAIN_MODEL"] = "haiku"
os.environ["NEATLOGS_API_KEY"] = "test-not-a-real-key-0000000000"  # nothing from a test goes to the real project

import neatlogs  # noqa: E402

import trace_safety  # noqa: E402

PROVIDED_EMAIL = "qa.tester@example.org"
PROVIDED_PASSWORD = "Hunter2-Zebra-77!"

EXPORTED: list[str] = []  # every span as the exporter would receive it, after the mask


def recording_mask(span):
    masked = trace_safety.mask(span)
    EXPORTED.append(json.dumps(masked, default=str))
    return masked


neatlogs.init(
    api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-user-tests",
    register_shutdown_handlers=False, mask=recording_mask,
)

if os.environ.get("HARNESS_DISABLE_PROTECTIONS"):
    # Negative control for test_credentials.py: with nothing registered, nothing is scrubbed or
    # redacted, so the searches in the test must find the login where the page showed it.
    trace_safety.register_secret = lambda *args, **kwargs: None

import anthropic.resources.beta.messages as beta_messages  # noqa: E402
import anthropic.resources.messages as plain_messages  # noqa: E402
import credentials as credentials_module  # noqa: E402
import db  # noqa: E402
import egress  # noqa: E402
import worker_run  # noqa: E402

# ------------------------------------------------------------------ the site under test

PAGE = "<!doctype html><html><head><title>{title}</title></head><body>{body}</body></html>"


class Site:
    def __init__(self, signup_mode: str = "app", landing: str = "normal"):
        self.signup_mode, self.landing = signup_mode, landing
        self.logins: list[dict] = []
        self.signups: list[dict] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, body: str, status: int = 200, headers: dict | None = None):
                data = PAGE.format(title="Acme Projects", body=body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/":
                    if site.landing == "third_party_only":
                        self._send(
                            "<h1>Acme Projects</h1><p>Plan and track your team's projects.</p>"
                            "<button type=button>Continue with Google</button> "
                            "<button type=button>Continue with GitHub</button>"
                        )
                    else:
                        self._send(
                            "<h1>Acme Projects</h1><p>Plan and track your team's projects.</p>"
                            "<a href='/login'>Log in</a> | <a href='/signup'>Sign up</a>"
                        )
                elif path == "/login":
                    self._send(self._login_form())
                elif path == "/signup":
                    self._send(
                        "<h1>Create your account</h1><form method=post action=/signup>"
                        "<label>Email <input name=email type=email></label><br>"
                        "<label>Password <input name=password type=password autocomplete=new-password></label><br>"
                        "<label>Confirm password <input name=confirm type=password></label><br>"
                        "<label><input type=checkbox name=terms> I agree to the Terms</label><br>"
                        "<button type=submit>Create account</button></form>"
                    )
                elif path == "/app":
                    email = (self.headers.get("Cookie", "").split("who=")[-1].split(";")[0]
                             if "who=" in self.headers.get("Cookie", "") else "")
                    self._send(
                        f"<h1>Projects</h1><p id=who>Welcome, {email}</p><ul><li>Apollo</li><li>Borealis</li></ul>"
                    )
                else:
                    self._send("<h1>Not found</h1>", 404)

            def _login_form(self, error: str = ""):
                return (
                    "<h1>Log in</h1>" + (f"<p role=alert>{error}</p>" if error else "")
                    + "<form method=post action=/login>"
                    "<label>Email <input name=email type=email></label><br>"
                    "<label>Password <input name=password type=password></label><br>"
                    "<button type=submit>Log in</button></form>"
                )

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                if self.path == "/login":
                    ok = form.get("email") == PROVIDED_EMAIL and form.get("password") == PROVIDED_PASSWORD
                    site.logins.append({"email": form.get("email"), "password_ok": ok})
                    if ok:
                        self._send("", 302, {"Location": "/app", "Set-Cookie": f"who={form['email']}; Path=/"})
                    else:
                        self._send(self._login_form("Invalid email or password"))
                elif self.path == "/signup":
                    site.signups.append({
                        "email": form.get("email"), "password": form.get("password"),
                        "confirm": form.get("confirm"), "terms": "terms" in form,
                    })
                    if site.signup_mode == "verify":
                        self._send("<h1>Almost there</h1><p>Check your email to verify your account. "
                                   "We have sent you a confirmation link.</p>")
                    else:
                        self._send("", 302, {"Location": "/app", "Set-Cookie": f"who={form.get('email', '')}; Path=/"})
                else:
                    self._send("<h1>Not found</h1>", 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


# ------------------------------------------------------------------ the stand-in database

class FakeDatabase:
    def __init__(self):
        self.secrets: dict[str, tuple[str, str]] = {}
        self.writes: list[dict] = []

    def install(self):
        fake = self

        async def take_run_secrets(run_id):
            row = fake.secrets.pop(run_id, None)
            return {"email": row[0], "password": row[1]} if row else None

        async def delete_run_secrets(run_id):
            fake.secrets.pop(run_id, None)

        async def finish_run(run_id, result, agent_version, brain_model):
            fake.writes.append({"kind": "finish_run", "run_id": run_id, "result": result})

        async def fail_run(run_id, error, agent_version=None, brain_model=None, result=None):
            fake.writes.append({"kind": "fail_run", "run_id": run_id, "error": error, "result": result})

        class Recorder:
            def __init__(self, run_id):
                self.run_id = run_id

            async def upload_screenshot(self, path):
                return f"https://stand-in.invalid/{self.run_id}/{path.name}"

            async def step(self, idx, tool, thought, input, result, url, screenshot_url):
                fake.writes.append({"kind": "step", "idx": idx, "tool": tool, "thought": thought, "input": input,
                                    "result": result, "url": url, "screenshot_url": screenshot_url})

            async def friction(self, step_idx, kind, severity, expected, happened):
                fake.writes.append({"kind": "friction", "step_idx": step_idx, "friction_kind": kind,
                                    "expected": expected, "happened": happened})

            async def first_impression(self, review):
                fake.writes.append({"kind": "first_impression", "review": review})

        db.take_run_secrets, db.delete_run_secrets = take_run_secrets, delete_run_secrets
        db.finish_run, db.fail_run, db.RunRecorder = finish_run, fail_run, Recorder


# ------------------------------------------------------------------ what leaves the process

OTHER_RUNS_SECRET = "Other-Tenant-Pw-9911!"  # registered, never used on a page: another run's login
MODEL_REQUESTS: list[str] = []  # the text of every request to a model, images left out
PAGE_SCRIPTS: list[str] = []  # every script the worker sent into a page, as text
PAGE_PROBES: list[dict] = []  # what the page showed while a screenshot or read was taken


def _text_of(value) -> str:
    def strip(node):
        if isinstance(node, dict):
            if node.get("type") == "image":
                return {"type": "image"}
            return {k: strip(v) for k, v in node.items()}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return json.dumps(strip(value), default=str)


def install_recorders(secret_values: list[str]):
    import stagehand.page as stagehand_page

    original_evaluate = stagehand_page.Page.evaluate

    async def recording_evaluate(self, expression, *args, **kwargs):
        PAGE_SCRIPTS.append(expression)
        return await original_evaluate(self, expression, *args, **kwargs)

    stagehand_page.Page.evaluate = recording_evaluate

    for cls in (beta_messages.AsyncMessages, plain_messages.AsyncMessages):
        original = cls.create

        async def recording_create(self, *args, _original=original, **kwargs):
            MODEL_REQUESTS.append(_text_of({k: kwargs.get(k) for k in ("system", "messages", "tools")}))
            return await _original(self, *args, **kwargs)

        cls.create = recording_create

    real = credentials_module.redacted_page

    @asynccontextmanager
    async def probing(page):
        async with real(page):
            seen = await page.evaluate(
                "(document.body ? document.body.innerText : '') + ' ' + "
                "[...document.querySelectorAll('input, textarea')].map((i) => i.value).join(' ')"
            )
            shows = any(v and v in seen for v in secret_values)
            PAGE_PROBES.append({"shows_a_secret": shows})
            yield

    credentials_module.redacted_page = probing


# ------------------------------------------------------------------ scenarios

SCENARIOS = {
    "test_login": {
        "site": {},
        "start": "/login",
        "goal": "Sign in with the test account and tell me the name of the first project on the dashboard.",
        "test_login": True,
    },
    "self_signup": {
        "site": {"signup_mode": "app"},
        "start": None,
        "goal": "Create an account and tell me the name of the first project on the dashboard.",
        "test_login": False,
    },
    "needs_verification": {
        "site": {"signup_mode": "verify"},
        "start": None,
        "goal": "Create an account and open the dashboard.",
        "test_login": False,
    },
    "third_party_only": {
        "site": {"landing": "third_party_only"},
        "start": None,
        "goal": "Get into the app and open the dashboard.",
        "test_login": False,
    },
}


async def run_scenario(name: str) -> dict:
    spec = SCENARIOS[name]
    site = Site(**spec["site"])
    fake = FakeDatabase()
    fake.install()
    run_id = str(uuid.uuid4())
    if spec["test_login"]:
        fake.secrets[run_id] = (PROVIDED_EMAIL, PROVIDED_PASSWORD)
    run = {
        "id": run_id, "url": site.base + "/", "goal": spec["goal"],
        "start_url": site.base + spec["start"] if spec["start"] else None,
        "has_test_login": spec["test_login"],
    }
    before = {"requests": len(MODEL_REQUESTS), "exported": len(EXPORTED), "probes": len(PAGE_PROBES),
              "scripts": len(PAGE_SCRIPTS)}
    try:
        await worker_run.execute(run, "harness")
    finally:
        site.close()
    return {
        "scenario": name,
        "db_writes": fake.writes,
        "secrets_left_in_database": {k: "present" for k in fake.secrets},
        "site_received": {"logins": site.logins, "signups": site.signups},
        "exported_spans": EXPORTED[before["exported"]:],
        "model_requests": MODEL_REQUESTS[before["requests"]:],
        "page_probes": PAGE_PROBES[before["probes"]:],
        "page_scripts": PAGE_SCRIPTS[before["scripts"]:],
        "start_url": run["start_url"],
    }


async def main(report_path: str, names: list[str]) -> None:
    # Loopback addresses are blocked by the egress guard; the test site counts as public, as in test_egress.
    original = egress.is_blocked_address
    egress.is_blocked_address = lambda address: False if str(address) == "127.0.0.1" else original(address)
    install_recorders([PROVIDED_EMAIL, PROVIDED_PASSWORD])
    # Another run's login, still registered in this process, must never be sent into any page.
    trace_safety.register_secret(OTHER_RUNS_SECRET, "[redacted]")
    reports = []
    for name in names:
        print(f"--- scenario {name}", flush=True)
        reports.append(await run_scenario(name))
    Path(report_path).write_text(json.dumps(reports, default=str), encoding="utf-8")
    neatlogs.flush()
    neatlogs.shutdown()
    print(f"HARNESS_REPORT {report_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:] or list(SCENARIOS)))
