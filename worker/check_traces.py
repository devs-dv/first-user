"""Check that each visit produces one clean neatlogs trace.

Usage: python check_traces.py [--cases ID ...]

Runs eval cases from evals/sites.json one after another, as the worker does (inside
neatlogs.identify), with no database. Every span is collected locally from the same
tracer provider that exports to neatlogs, and neatlogs' own record of what it exports
is read from NEATLOGS_LOG_SPANS. For each visit it checks:

  one trace       every span started during the visit has the visit's trace id
  no orphans      every span's parent exists in the same trace and was exported
  all ended       every span that started has ended
  root ends last  no span ends after the visit's root span
  no ERROR        no span has ERROR status on a run that finished normally
"""

import argparse
import asyncio
import json
import os
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

EXPORT_LOG = Path(tempfile.gettempdir()) / f"first-user-spans-{os.getpid()}.log"
os.environ["NEATLOGS_LOG_SPANS"] = "1"
os.environ["NEATLOGS_LOG_SPANS_FILE"] = str(EXPORT_LOG)

os.environ.setdefault("FIRST_USER_ENVIRONMENT", "development")  # not a production run
import neatlogs  # noqa: E402
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider  # noqa: E402
from opentelemetry.trace import StatusCode  # noqa: E402

CASES = json.loads((Path(__file__).parent.parent / "evals" / "sites.json").read_text(encoding="utf-8"))["cases"]


class Collector(SpanProcessor):
    def __init__(self):
        self.started, self.ended = [], []

    def on_start(self, span, parent_context=None):
        self.started.append(span)

    def on_end(self, span):
        self.ended.append(span)


collector = Collector()
provider = TracerProvider()
provider.add_span_processor(collector)
neatlogs.init(api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-visit-test", tracer_provider=provider)

from visit import first_visit  # noqa: E402

INTERNAL = {"neatlogs.trace.complete"}  # neatlogs' own completion marker, outside the trace tree


def exported() -> dict[str, dict]:
    if not EXPORT_LOG.exists():
        return {}
    spans = {}
    for line in EXPORT_LOG.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        spans[entry["span_id"]] = entry
    return spans


def span_id(span) -> str:
    return format(span.context.span_id, "016x")


def trace_id(span) -> str:
    return format(span.context.trace_id, "032x")


def analyse(case_id: str, started: list, ended: list, result: dict | None, error: str | None) -> dict:
    spans = [s for s in started if s.name not in INTERNAL]
    ended_ids = {span_id(s) for s in ended}
    roots = [s for s in spans if s.name == "first_visit"]
    root = roots[0] if roots else None
    root_trace = trace_id(root) if root else None
    by_id = {span_id(s): s for s in spans}
    exports = exported()

    traces = Counter(trace_id(s) for s in spans)
    stray = [s for s in spans if trace_id(s) != root_trace]
    orphans = []
    for s in spans:
        if s is root or s.parent is None:
            if s is not root:
                orphans.append((s.name, "no parent (a separate root)"))
            continue
        parent_id = format(s.parent.span_id, "016x")
        parent = by_id.get(parent_id)
        if parent is None:
            orphans.append((s.name, "parent not collected"))
        elif trace_id(parent) != trace_id(s):
            orphans.append((s.name, "parent in another trace"))
        elif exports and parent_id not in exports:
            orphans.append((s.name, f"parent {parent.name} not exported"))
    unended = [s.name for s in spans if span_id(s) not in ended_ids]
    late = [s.name for s in spans if root and s is not root and s.end_time and root.end_time
            and s.end_time > root.end_time]
    errors = [(s.name, s.status.description or "") for s in spans
              if s.status.status_code == StatusCode.ERROR]
    exported_root = exports.get(span_id(root)) if root else None
    finished_normally = error is None and result is not None and result.get("outcome") != "error"
    return {
        "case": case_id,
        "outcome": result.get("outcome") if result else None,
        "run_error": error,
        "root_trace_id": root_trace,
        "spans": len(spans),
        "traces": len(traces),
        "stray_traces": {t: sorted(Counter(s.name for s in stray if trace_id(s) == t).items())
                         for t in traces if t != root_trace},
        "orphans": orphans,
        "unended": unended,
        "ended_after_root": late,
        "error_spans": errors,
        "checks": {
            "one trace per visit": len(traces) == 1,
            "no orphan spans": not orphans,
            "every span ended": not unended,
            "no span ends after the root": not late,
            "no ERROR span on a normal run": not (finished_normally and errors),
            "exported root has the same trace id": bool(exported_root) and exported_root.get("trace_id",
                                                                                                "").replace("0x", "") == root_trace,
            "one egress_summary span": sum(s.name == "egress_summary" for s in spans) == 1,
        },
        "span_names": sorted(Counter(s.name for s in spans).items()),
    }


async def guard_scenarios() -> dict:
    """The egress guard used without a run (as tests and scripts do), and closed mid-check."""
    import egress
    import socket

    first = len(collector.started)
    guard = egress.EgressGuard()
    await guard.start()
    for target in ("CONNECT example.com:443 HTTP/1.1", "CONNECT 127.0.0.2:443 HTTP/1.1"):
        reader, writer = await asyncio.open_connection("127.0.0.1", guard.port)
        writer.write((target + "\r\n\r\n").encode())
        await writer.drain()
        await reader.readline()
        writer.close()
    await guard.close()
    no_run = collector.started[first:]

    # Closed while a host check is still resolving.
    first = len(collector.started)
    loop = asyncio.get_running_loop()
    original = loop.getaddrinfo

    async def slow_getaddrinfo(*args, **kwargs):
        await asyncio.sleep(30)
        return await original(*args, **kwargs)

    async with _root("guard_close_mid_check"):
        guard = egress.EgressGuard()
        await guard.start()
        loop.getaddrinfo = slow_getaddrinfo
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", guard.port)
            writer.write(b"CONNECT slow.example.com:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            await asyncio.sleep(0.5)
            await guard.close()
            writer.close()
        finally:
            loop.getaddrinfo = original
    mid_check = collector.started[first:]

    # A refusal during a run: one span, in the run's trace.
    first = len(collector.started)
    async with _root("guard_refusal_in_run"):
        guard = egress.EgressGuard()
        await guard.start()
        for target in ("CONNECT example.com:443 HTTP/1.1", "CONNECT 127.0.0.2:443 HTTP/1.1"):
            reader, writer = await asyncio.open_connection("127.0.0.1", guard.port)
            writer.write((target + "\r\n\r\n").encode())
            await writer.drain()
            await reader.readline()
            writer.close()
        await guard.close()
        egress.summary_span(guard.summary())
    in_run = collector.started[first:]
    return {
        "guard refusal during a run": {
            "spans": sorted(Counter(s.name for s in in_run).items()),
            "traces": len({trace_id(s) for s in in_run}),
            "summary": guard.summary(),
        },
        "guard without a run": {"spans": len(no_run), "traces": len({trace_id(s) for s in no_run}),
                                "names": sorted(Counter(s.name for s in no_run).items())},
        "guard closed mid-check": {"spans": [(s.name, s.status.status_code.name) for s in mid_check],
                                   "error_spans": sum(s.status.status_code == StatusCode.ERROR for s in mid_check)},
    }


class _root:
    """A WORKFLOW root span around a block, like first_visit."""

    def __init__(self, name):
        self.name = name

    async def __aenter__(self):
        self.cm = neatlogs.trace(self.name, kind="WORKFLOW")
        self.cm.__enter__()

    async def __aexit__(self, *exc):
        self.cm.__exit__(*exc)


async def visit(case: dict, run_id: str) -> tuple[dict | None, str | None]:
    try:
        with neatlogs.identify(session_id=f"run_{run_id}"):
            return await first_visit(case["url"], case["goal"], run_id), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"[:300]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="*", default=["saucedemo_standard", "herokuapp_add_remove", "uitesting_click"])
    args = parser.parse_args()
    cases = [c for c in CASES if c["id"] in args.cases]
    reports = []

    async def all_visits():
        # One event loop for every visit, as in the worker.
        for case in cases:
            run_id = f"traces-{case['id']}-{datetime.now():%H%M%S}"
            first_started, first_ended = len(collector.started), len(collector.ended)
            result, error = await visit(case, run_id)
            await asyncio.sleep(2)  # let any late background work show up
            neatlogs.flush()
            report = analyse(case["id"], collector.started[first_started:], collector.ended[first_ended:],
                             result, error)
            if result is not None:
                report["checks"]["trace id saved on the result"] = result.get("trace_id") == report["root_trace_id"]
            reports.append(report)
            print(json.dumps(reports[-1], indent=2), flush=True)
        return await guard_scenarios()

    scenarios = asyncio.run(all_visits())
    print(json.dumps(scenarios, indent=2), flush=True)
    summary = {
        "visits": len(reports),
        "traces_per_visit": [r["traces"] for r in reports],
        "orphan_spans": sum(len(r["orphans"]) for r in reports),
        "error_spans": sum(len(r["error_spans"]) for r in reports),
        "unended_spans": sum(len(r["unended"]) for r in reports),
        "spans_ending_after_root": sum(len(r["ended_after_root"]) for r in reports),
        "all_checks_pass": all(all(r["checks"].values()) for r in reports),
        "guard_scenarios": scenarios,
    }
    print(json.dumps(summary, indent=2))
    out = Path(__file__).parent / "runs" / f"check-traces-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "visits": reports}, indent=2), encoding="utf-8")
    neatlogs.shutdown()
    provider.shutdown()
    EXPORT_LOG.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
