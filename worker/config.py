import os


def _flag(name: str, default: bool) -> bool:
    """A true/false setting from the environment: 1, true, yes or on mean true."""
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


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

# A generous ceiling on the visitor's turns. The real limit is the budget below (MAX_RUN_TOKENS and
# MAX_RUN_COST_USD), which ends a run as "gave_up" whatever the step count.
MAX_STEPS = int(os.environ.get("MAX_STEPS", "20"))
# With this many steps left, the agent is told to conclude and call finish.
WRAP_UP_STEPS = int(os.environ.get("WRAP_UP_STEPS", "2"))

# The first page load waits for the DOM (not the full load event), up to this long. A page
# that still has not finished parsing by then is used as it is.
PAGE_READY_TIMEOUT_MS = int(os.environ.get("PAGE_READY_TIMEOUT_MS", "75000"))

# Independent check of an "achieved" verdict: sees only the goal and the final page.
VERIFIER_MODEL = os.environ.get("VERIFIER_MODEL", "claude-haiku-5-5")
# Report v2: a verdict, run facts, structured fix prompts with acceptance criteria and evidence bases.
# REPORT_V2=false turns all of it off in the worker (the old report is written); the web app has its own flags.
REPORT_V2 = _flag("REPORT_V2", True)
# Check again: a run queued as a retest (runs.retest_of) is compared with its original. CHECK_AGAIN=false
# makes such a run an ordinary visit, with no guided follow-up and no comparison.
CHECK_AGAIN = _flag("CHECK_AGAIN", True)
# Writes the report's findings after the visit (report_writer.py); one call per visit.
REPORT_MODEL = os.environ.get("REPORT_MODEL", VERIFIER_MODEL)

ACT_TIMEOUT_MS = int(os.environ.get("ACT_TIMEOUT_MS", "30000"))

# Coordinate clicks missed their targets at Windows' 125% display scaling.
DEVICE_SCALE_FACTOR = float(os.environ.get("DEVICE_SCALE_FACTOR", "1.0"))

# ---- Running on a server (see DEPLOY.md). Locally the defaults give a visible Chrome window.
# HEADLESS=true runs Chrome with no window, which a server without a display needs.
HEADLESS = _flag("HEADLESS", False)
# The page's size, whatever the window looks like, so click coordinates mean the same everywhere.
VIEWPORT_WIDTH = int(os.environ.get("VIEWPORT_WIDTH", "1280"))
VIEWPORT_HEIGHT = int(os.environ.get("VIEWPORT_HEIGHT", "800"))
# Chrome's own sandbox needs kernel features Docker blocks by default; the image sets this to false
# and relies on the container instead (non-root user, no capabilities). Locally it stays on.
CHROME_SANDBOX = _flag("CHROME_SANDBOX", True)
# Delete a run's local screenshots once the run is saved (they are uploaded to storage). A server
# would otherwise fill its disk.
CLEAN_RUN_FILES = _flag("CLEAN_RUN_FILES", False)
# How often an idle worker logs a health line, and the file whose modification time is the heartbeat.
HEALTH_INTERVAL_SECONDS = int(os.environ.get("HEALTH_INTERVAL_SECONDS", "60"))
HEALTH_FILE = os.environ.get("HEALTH_FILE", "/tmp/first-user-worker.heartbeat")

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
