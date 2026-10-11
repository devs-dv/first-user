"""Run one visit and check that three cost sources agree, and that lookup LLM spans nest under tools.

Usage: python check_costs.py --url URL --goal "GOAL" [--stub-recorder]

--stub-recorder stands in for the database: screenshots get placeholder URLs
(https://stub.invalid/...) and steps are kept in memory, so the screenshot_url
path can be checked without writing to Supabase.

The three sources:
  ours       RunUsage, built from each Anthropic response (costs.py)
  stagehand  Stagehand's metrics(), which counts the usage our callback reports back
  spans      the neatlogs LLM spans, collected locally from the same tracer provider
             that exports them to neatlogs
"""

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

import neatlogs
from dotenv import load_dotenv
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider

load_dotenv(Path(__file__).parent / ".env")


class Collector(SpanProcessor):
    def __init__(self):
        self.spans = []

    def on_end(self, span):
        self.spans.append(span)


collector = Collector()
provider = TracerProvider()
provider.add_span_processor(collector)
neatlogs.init(
    api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-visit-test", tracer_provider=provider
)

from config import BRAIN_MODEL, LOOKUP_VIA  # noqa: E402
from costs import _price, CACHE_READ_MULTIPLIER, CACHE_WRITE_MULTIPLIER  # noqa: E402
from visit import first_visit  # noqa: E402

LOOKUP_PARENTS = {"look", "do.rung_a_act", "do.rung_b_observe_act"}


class StubRecorder:
    def __init__(self, run_id: str):
        self.run_id, self.steps, self.frictions = run_id, [], []

    async def upload_screenshot(self, path: Path) -> str:
        return f"https://stub.invalid/{self.run_id}/{path.name}"

    async def step(self, idx, tool, thought, input, result, url, screenshot_url) -> None:
        self.steps.append({"idx": idx, "tool": tool, "screenshot_url": screenshot_url})

    async def friction(self, step_idx, kind, severity, expected, happened) -> None:
        self.frictions.append({"step_idx": step_idx, "kind": kind})


def span_tokens(spans) -> dict:
    def total(key):
        return sum(int(s.attributes.get(f"neatlogs.llm.token_count.{key}", 0)) for s in spans)

    tally = {
        "calls": len(spans),
        "input": total("prompt"),
        "cache_write": total("cache_write"),
        "cache_read": total("cache_read"),
        "output": total("completion"),
    }
    cost = 0.0
    for s in spans:
        input_price, output_price = _price(str(s.attributes.get("neatlogs.llm.model_name", "")))
        a = s.attributes
        cost += (
            int(a.get("neatlogs.llm.token_count.prompt", 0)) * input_price
            + int(a.get("neatlogs.llm.token_count.cache_write", 0)) * input_price * CACHE_WRITE_MULTIPLIER
            + int(a.get("neatlogs.llm.token_count.cache_read", 0)) * input_price * CACHE_READ_MULTIPLIER
            + int(a.get("neatlogs.llm.token_count.completion", 0)) * output_price
        ) / 1_000_000
    tally["cost"] = round(cost, 5)
    return tally


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--stub-recorder", action="store_true")
    args = parser.parse_args()

    run_id = "check-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Run {run_id}: {args.url} (brain {BRAIN_MODEL}, lookup via {LOOKUP_VIA})", flush=True)
    try:
        recorder = StubRecorder(run_id) if args.stub_recorder else None
        result = asyncio.run(first_visit(args.url, args.goal, run_id, recorder=recorder))
    finally:
        neatlogs.flush()

    by_id = {s.context.span_id: s for s in collector.spans}

    def parent_of(span):
        return by_id.get(span.parent.span_id) if span.parent else None

    # One model call = one span from the wrapped client (it has the provider attribute).
    llm = sorted((s for s in collector.spans if s.attributes.get("neatlogs.llm.provider")),
                 key=lambda s: s.start_time)
    parent = {id(s): getattr(parent_of(s), "name", None) for s in llm}
    lookup_spans = [s for s in llm if parent[id(s)] != "persona_run"]
    brain_spans = [s for s in llm if parent[id(s)] == "persona_run"]
    other_llm_kind = [s for s in collector.spans if s.attributes.get("openinference.span.kind") == "LLM"]

    def system_text(span):
        a = span.attributes
        return a.get("neatlogs.llm.input_messages.0.content") if a.get(
            "neatlogs.llm.input_messages.0.role") == "system" else None

    def tokens(span, key):
        return int(span.attributes.get(f"neatlogs.llm.token_count.{key}", 0))

    usage = result["usage"]
    lookup, brain, metrics = usage["lookup_tokens"], usage["brain_tokens"], usage["stagehand_metrics"]
    lookup_input = lookup.get("input", 0) + lookup.get("cache_write", 0) + lookup.get("cache_read", 0)
    spans_lookup, spans_brain = span_tokens(lookup_spans), span_tokens(brain_spans)
    report = {
        "run_id": run_id,
        "outcome": result["outcome"],
        "reason": result["reason"],
        "steps": result["steps"],
        "cost_usd": usage["estimated_cost_usd"],
        "lookup": {
            "ours": lookup,
            "spans": spans_lookup,
            "stagehand_metrics": metrics,
        },
        "brain": {"ours": brain, "spans": spans_brain},
        "lookup_span_parents": dict(Counter(parent[id(s)] for s in lookup_spans)),
        "brain_turns": [
            {"cache_write": tokens(sp, "cache_write"), "cache_read": tokens(sp, "cache_read"),
             "uncached_input": tokens(sp, "prompt"), "output": tokens(sp, "completion")}
            for sp in brain_spans
        ],
        "checks": {
            "lookup calls: ours == spans": lookup.get("calls") == spans_lookup["calls"],
            "lookup tokens: ours == spans": all(lookup.get(k) == spans_lookup[k]
                                                 for k in ("input", "cache_write", "cache_read", "output")),
            "lookup input: ours == stagehand prompt": lookup_input == metrics["prompt"],
            "lookup output: ours == stagehand completion": lookup.get("output") == metrics["completion"],
            "lookup cache reads: ours == stagehand cached": lookup.get("cache_read") == metrics["cached_input"],
            "brain tokens: ours == spans": all(brain[k] == spans_brain[k]
                                                for k in ("calls", "input", "cache_write", "cache_read", "output")),
            "cost: ours == spans": abs(spans_lookup["cost"] + spans_brain["cost"]
                                   - usage["estimated_cost_usd"]["total"]) < 2e-5,
            "every lookup span is under look or rung a/b": set(parent[id(s)] for s in lookup_spans) <= LOOKUP_PARENTS,
            "one LLM span per model call (no trace(kind=LLM) wrappers)": not other_llm_kind
            and len(llm) == lookup.get("calls", 0) + brain["calls"],
            "system prompt recorded as plain text on every LLM span": all(
                (t := system_text(sp)) and not t.lstrip().startswith("[{") for sp in llm),
            "every brain turn after the first reads from the cache": all(
                tokens(sp, "cache_read") > 0 for sp in brain_spans[1:]),
        },
    }
    do_outputs = [json.loads(s.attributes.get("output.value", "{}")) for s in collector.spans if s.name == "do"]
    brain_inputs = " ".join(str(v) for s in brain_spans for k, v in s.attributes.items() if "input_messages" in k)
    report["screenshots"] = {
        "do_spans": len(do_outputs),
        "with_screenshot_url": sum("screenshot_url" in o for o in do_outputs),
        "recorded_steps_with_url": sum(bool(step["screenshot_url"]) for step in recorder.steps) if recorder else None,
    }
    report["checks"]["every do span output has screenshot_url only when a recorder is set"] = all(
        ("screenshot_url" in o) == (recorder is not None) for o in do_outputs)
    report["checks"]["the brain model never sees screenshot_url"] = "screenshot_url" not in brain_inputs
    print(json.dumps(report, indent=2))
    out = Path(__file__).parent / "runs" / f"{run_id}-costs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    neatlogs.shutdown()
    provider.shutdown()


if __name__ == "__main__":
    main()
