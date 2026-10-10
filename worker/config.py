import os

# The model that plays the first-time visitor (Anthropic Messages API).
BRAIN_MODEL = os.environ.get("BRAIN_MODEL", "claude-sonnet-5-5")

# The model Stagehand uses to find elements for act/observe/extract.
# Stagehand 4.2.0 validates model names against a fixed list; the newest Haiku it accepts is 4.5.
LOOKUP_MODEL = os.environ.get("LOOKUP_MODEL", "anthropic/claude-haiku-4-5")

MAX_STEPS = int(os.environ.get("MAX_STEPS", "20"))

ACT_TIMEOUT_MS = int(os.environ.get("ACT_TIMEOUT_MS", "30000"))
