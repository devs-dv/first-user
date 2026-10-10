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

# The model Stagehand uses to find elements for act/observe/extract.
# Stagehand 4.2.0 validates model names against a fixed list; the newest Haiku it accepts is 4.5.
LOOKUP_MODEL = os.environ.get("LOOKUP_MODEL", "anthropic/claude-haiku-4-5")

MAX_STEPS = int(os.environ.get("MAX_STEPS", "15"))

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
