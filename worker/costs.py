"""Token and cost accounting for one run: the brain model, Stagehand's lookup model and the verifier.

Each model call is counted once. Brain and verifier responses are always added here. Lookup
calls are counted from our own callback's responses when LOOKUP_VIA is
"callback", and from Stagehand's cumulative metrics() otherwise; in callback
mode the metrics snapshot is kept only to cross-check our own count.
"""

from dataclasses import dataclass, field

from config import LOOKUP_CALLBACK_MODEL, LOOKUP_MODEL, LOOKUP_VIA, PRICES

CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


def _price(model: str) -> tuple[float, float]:
    return PRICES.get(model.removeprefix("anthropic/"), (0.0, 0.0))


def response_cost(response) -> float:
    """USD for one Anthropic Messages response, cache writes and reads included."""
    usage = response.usage
    input_price, output_price = _price(response.model)
    return (
        usage.input_tokens * input_price
        + (usage.cache_creation_input_tokens or 0) * input_price * CACHE_WRITE_MULTIPLIER
        + (usage.cache_read_input_tokens or 0) * input_price * CACHE_READ_MULTIPLIER
        + usage.output_tokens * output_price
    ) / 1_000_000


@dataclass
class TokenTally:
    """Anthropic-style token counts: `input` excludes cache writes and reads."""

    calls: int = 0
    input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0
    cost: float = 0.0
    models: set[str] = field(default_factory=set)

    def add(self, response) -> None:
        usage = response.usage
        self.calls += 1
        self.input += usage.input_tokens
        self.cache_write += usage.cache_creation_input_tokens or 0
        self.cache_read += usage.cache_read_input_tokens or 0
        self.output += usage.output_tokens
        self.cost += response_cost(response)
        self.models.add(response.model)

    @property
    def total_tokens(self) -> int:
        return self.input + self.cache_write + self.cache_read + self.output

    def summary(self) -> dict:
        return {
            "models": sorted(self.models),
            "calls": self.calls,
            "input": self.input,
            "cache_write": self.cache_write,
            "cache_read": self.cache_read,
            "output": self.output,
        }


@dataclass
class RunUsage:
    brain: TokenTally = field(default_factory=TokenTally)
    lookup: TokenTally = field(default_factory=TokenTally)
    verifier: TokenTally = field(default_factory=TokenTally)
    review: TokenTally = field(default_factory=TokenTally)
    # Stagehand's metrics() for the session; cumulative, so the latest snapshot is stored.
    stagehand_prompt: int = 0
    stagehand_completion: int = 0
    stagehand_cached: int = 0

    def add_response(self, response) -> None:
        self.brain.add(response)

    def add_lookup_response(self, response) -> None:
        self.lookup.add(response)

    def add_verifier_response(self, response) -> None:
        self.verifier.add(response)

    def add_review_response(self, response) -> None:
        self.review.add(response)

    def set_stagehand(self, metrics) -> None:
        self.stagehand_prompt = int(metrics.total_prompt_tokens)
        self.stagehand_completion = int(metrics.total_completion_tokens)
        self.stagehand_cached = int(metrics.total_cached_input_tokens)

    @property
    def lookup_tokens(self) -> int:
        if LOOKUP_VIA == "callback":
            return self.lookup.total_tokens
        return self.stagehand_prompt + self.stagehand_completion

    @property
    def lookup_cost(self) -> float:
        if LOOKUP_VIA == "callback":
            return self.lookup.cost
        return metrics_cost(self.stagehand_prompt, self.stagehand_completion, self.stagehand_cached)

    @property
    def total_tokens(self) -> int:
        return self.brain.total_tokens + self.lookup_tokens + self.verifier.total_tokens + self.review.total_tokens

    @property
    def total_cost(self) -> float:
        return self.brain.cost + self.lookup_cost + self.verifier.cost + self.review.cost

    def summary(self) -> dict:
        return {
            "brain_tokens": self.brain.summary(),
            "lookup_via": LOOKUP_VIA,
            "lookup_tokens": (
                self.lookup.summary() if LOOKUP_VIA == "callback" else {"models": [LOOKUP_MODEL]}
            ),
            "verifier_tokens": self.verifier.summary(),
            "review_tokens": self.review.summary(),
            "stagehand_metrics": {
                "prompt": self.stagehand_prompt,
                "completion": self.stagehand_completion,
                "cached_input": self.stagehand_cached,
            },
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": {
                "brain": round(self.brain.cost, 5),
                "lookup": round(self.lookup_cost, 5),
                "verifier": round(self.verifier.cost, 5),
                "review": round(self.review.cost, 5),
                "total": round(self.total_cost, 5),
            },
        }


def metrics_cost(prompt: int, completion: int, cached: int) -> float:
    """USD for Stagehand's own token counts, where prompt tokens include cached ones."""
    model = LOOKUP_CALLBACK_MODEL if LOOKUP_VIA == "callback" else LOOKUP_MODEL
    input_price, output_price = _price(model)
    uncached = max(prompt - cached, 0)
    return (
        uncached * input_price + cached * input_price * CACHE_READ_MULTIPLIER + completion * output_price
    ) / 1_000_000
