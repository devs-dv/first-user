"""Run one visit and check that three cost sources agree, and that lookup LLM spans nest under tools.

Usage: python check_costs.py --url URL --goal "GOAL"

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
    args = parser.parse_args()

    run_id = "check-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Run {run_id}: {args.url} (brain {BRAIN_MODEL}, lookup via {LOOKUP_VIA})", flush=True)
    try:
        result = asyncio.run(first_visit(args.url, args.goal, run_id))
    finally:
        neatlogs.flush()

    names = {s.context.span_id: s.name for s in collector.spans}
    llm = [s for s in collector.spans if s.attributes.get("neatlogs.span.kind") == "llm"]
    parent = {id(s): names.get(s.parent.span_id) if s.parent else None for s in llm}
    lookup_spans = [s for s in llm if parent[id(s)] != "persona_run"]
    brain_spans = [s for s in llm if parent[id(s)] == "persona_run"]

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
        },
    }
    print(json.dumps(report, indent=2))
    out = Path(__file__).parent / "runs" / f"{run_id}-costs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    neatlogs.shutdown()
    provider.shutdown()


if __name__ == "__main__":
    main()
