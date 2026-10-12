"""Import this first in every test module: it makes sure no test ever sends a trace to neatlogs.

Why not just switch export off: with export off, neatlogs skips its masking pipeline, and the
credential tests exist to check what that pipeline would have sent. So tests run the real pipeline and
point it at a sink on this machine that accepts and discards every request. Nothing leaves the
machine, whatever key is in the environment.

What it does, before neatlogs or anything that uses it is imported:

  - NEATLOGS_ENDPOINT is set to the local sink (and kept there: a later `neatlogs.init(endpoint=...)` is
    overridden), so auto-started and explicitly started clients both export to it;
  - dotenv's load_dotenv is wrapped so a key loaded from a .env file is replaced by a placeholder, and
    the real key is never in a test process's environment (the file is read by dotenv, not by this code);
  - `sink_requests()` says how many batches the sink has received, so a test can prove the pipeline ran.

Real runs (worker/main.py) and evals (evals/run.py) never import this, so they reach the project.
`conftest.py` imports it for pytest; for unittest each test module imports it on its first line, and
test_no_export.py checks that every one does.
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLACEHOLDER_KEY = "test-never-exported-0000000000"

_received = {"batches": 0, "bytes": 0}


class _Sink(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        _received["batches"] += 1
        _received["bytes"] += length
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_sink() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Sink)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="neatlogs-test-sink").start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def sink_requests() -> int:
    """How many export requests the local sink has received in this process."""
    return _received["batches"]


def _install() -> str:
    # Inherited by a harness subprocess, so a live test's child process is covered too.
    existing = os.environ.get("NEATLOGS_TEST_SINK")
    if existing:
        endpoint = existing
    else:
        endpoint = _start_sink()
        os.environ["NEATLOGS_TEST_SINK"] = endpoint
    os.environ["NEATLOGS_ENDPOINT"] = endpoint
    os.environ["NEATLOGS_API_KEY"] = PLACEHOLDER_KEY

    import dotenv

    if not getattr(dotenv.load_dotenv, "_first_user_test_wrapper", False):
        real = dotenv.load_dotenv

        def load_dotenv(*args, **kwargs):
            result = real(*args, **kwargs)
            # Whatever the file said, the key and the endpoint stay the test ones.
            os.environ["NEATLOGS_API_KEY"] = PLACEHOLDER_KEY
            os.environ["NEATLOGS_ENDPOINT"] = endpoint
            return result

        load_dotenv._first_user_test_wrapper = True
        dotenv.load_dotenv = load_dotenv

    try:
        import neatlogs
    except ImportError:  # no SDK: nothing to keep from exporting
        return endpoint
    if not getattr(neatlogs.init, "_first_user_test_wrapper", False):
        real_init = neatlogs.init

        def init(*args, **kwargs):
            kwargs["endpoint"] = endpoint  # an explicit endpoint is overridden too
            if args:
                args = (PLACEHOLDER_KEY, *args[1:])
            else:
                kwargs["api_key"] = PLACEHOLDER_KEY
            return real_init(*args, **kwargs)

        init._first_user_test_wrapper = True
        neatlogs.init = init
    return endpoint


ENDPOINT = _install()
