import os
from pathlib import Path

import anthropic
import neatlogs
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

neatlogs.init(api_key=os.environ["NEATLOGS_API_KEY"], workflow_name="first-visit-test")

client = neatlogs.wrap(anthropic.Anthropic())

response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=1024,
    output_config={"effort": "low"},
    betas=["server-side-fallback-2026-07-01"],
    fallbacks="default",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)

if response.stop_reason == "refusal":
    raise SystemExit(f"Request was refused: {response.stop_details}")

print("".join(block.text for block in response.content if block.type == "text"))

neatlogs.flush()
neatlogs.shutdown()
