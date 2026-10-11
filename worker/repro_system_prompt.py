"""Reproduce the blank "System Prompt template:" on neatlogs LLM spans.

Usage: python repro_system_prompt.py

Makes two tiny claude-haiku-5-5 calls through a neatlogs-wrapped client, each
under its own WORKFLOW span so they are easy to find in the dashboard:

  repro_A_system_as_string          system="..."
  repro_B_system_as_cached_blocks   system=[{"type": "text", "text": "...", "cache_control": {...}}]

It prints the neatlogs and anthropic versions, and what each LLM span recorded
as its system message (collected locally from the provider that exports to neatlogs).
"""

import asyncio
import os
from importlib.metadata import version
from pathlib import Path

import neatlogs
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider

load_dotenv(Path(__file__).parent / ".env")

MODEL = "claude-haiku-5-5"
SYSTEM = "You are a terse assistant. Answer in one word."
QUESTION = "What colour is a clear daytime sky?"


class Collector(SpanProcessor):
    def __init__(self):
        self.spans = []

    def on_end(self, span):
        self.spans.append(span)


collector = Collector()
provider = TracerProvider()
provider.add_span_processor(collector)
neatlogs.init(
    api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="repro-system-prompt", tracer_provider=provider
)
client = neatlogs.wrap(AsyncAnthropic())


async def ask(system) -> str:
    response = await client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": QUESTION}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")


@neatlogs.span(kind="WORKFLOW", name="repro_A_system_as_string")
async def call_a() -> str:
    return await ask(SYSTEM)


@neatlogs.span(kind="WORKFLOW", name="repro_B_system_as_cached_blocks")
async def call_b() -> str:
    return await ask([{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}])


async def main() -> None:
    print(f"neatlogs {version('neatlogs')}, anthropic {version('anthropic')}, model {MODEL}")
    print(f"A answered: {await call_a()!r}")
    print(f"B answered: {await call_b()!r}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        neatlogs.flush()
    names = {s.context.span_id: s.name for s in collector.spans}
    for span in collector.spans:
        if span.attributes.get("neatlogs.span.kind") == "llm":
            parent = names.get(span.parent.span_id) if span.parent else None
            system = span.attributes.get("neatlogs.llm.input_messages.0.content")
            print(f"{parent}: recorded system message = {system!r}")
    neatlogs.shutdown()
    provider.shutdown()
