import os

# The model that plays the first-time visitor (Anthropic Messages API).
# BRAIN_MODEL takes a full model id or an alias: "haiku" is the cheap development option.
BRAIN_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
BRAIN_MODEL = BRAIN_MODEL_ALIASES.get(
    os.environ.get("BRAIN_MODEL", "sonnet"), os.environ.get("BRAIN_MODEL", "sonnet")
)
BRAIN_EFFORT = os.environ.get("BRAIN_EFFORT", "low")
MAX_TOKENS_PER_TURN = int(os.environ.get("MAX_TOKENS_PER_TURN", "2048"))

# How Stagehand reaches its lookup model for act/observe/extract:
#   "callback"   our neatlogs-wrapped Anthropic client (lookup_model.py), so each call is a traced LLM span
#   "model_name" Stagehand calls LOOKUP_MODEL itself; calls are invisible to neatlogs
LOOKUP_VIA = os.environ.get("LOOKUP_VIA", "callback")
LOOKUP_CALLBACK_MODEL = os.environ.get("LOOKUP_CALLBACK_MODEL", "claude-haiku-5-5")
LOOKUP_MAX_TOKENS = int(os.environ.get("LOOKUP_MAX_TOKENS", "4096"))
# Stagehand 4.2.0 validates model names against a fixed list; the newest Haiku it accepts is 4.5.
LOOKUP_MODEL = os.environ.get("LOOKUP_MODEL", "anthropic/claude-haiku-4-5")

MAX_STEPS = int(os.environ.get("MAX_STEPS", "15"))
# With this many steps left, the agent is told to conclude and call finish.
WRAP_UP_STEPS = int(os.environ.get("WRAP_UP_STEPS", "2"))

# The first page load waits for the DOM (not the full load event), up to this long. A page
# that still has not finished parsing by then is used as it is.
PAGE_READY_TIMEOUT_MS = int(os.environ.get("PAGE_READY_TIMEOUT_MS", "75000"))

# Independent check of an "achieved" verdict: sees only the goal and the final page.
VERIFIER_MODEL = os.environ.get("VERIFIER_MODEL", "claude-haiku-5-5")

ACT_TIMEOUT_MS = int(os.environ.get("ACT_TIMEOUT_MS", "30000"))

# Coordinate clicks missed their targets at Windows' 125% display scaling.
DEVICE_SCALE_FACTOR = float(os.environ.get("DEVICE_SCALE_FACTOR", "1.0"))

# Per-run budget: model plus Stagehand tokens (cache reads included), and estimated USD.
MAX_RUN_TOKENS = int(os.environ.get("MAX_RUN_TOKENS", "400000"))
MAX_RUN_COST_USD = float(os.environ.get("MAX_RUN_COST_USD", "0.30"))

# USD per million tokens: (input, output). Cache writes cost 1.25x input, cache reads 0.1x input.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
}
