"""Token and cost accounting for one run: the brain model plus Stagehand's lookup model."""

from dataclasses import dataclass, field

from config import LOOKUP_MODEL, PRICES

CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


def _price(model: str) -> tuple[float, float]:
    return PRICES.get(model.removeprefix("anthropic/"), (0.0, 0.0))


@dataclass
class RunUsage:
    model_input: int = 0
    model_cache_write: int = 0
    model_cache_read: int = 0
    model_output: int = 0
    model_cost: float = 0.0
    models_used: set[str] = field(default_factory=set)
    stagehand_prompt: int = 0
    stagehand_completion: int = 0
    stagehand_cached: int = 0

    def add_response(self, response) -> None:
        usage = response.usage
        cache_write = usage.cache_creation_input_tokens or 0
        cache_read = usage.cache_read_input_tokens or 0
        self.model_input += usage.input_tokens
        self.model_cache_write += cache_write
        self.model_cache_read += cache_read
        self.model_output += usage.output_tokens
        self.models_used.add(response.model)
        input_price, output_price = _price(response.model)
        self.model_cost += (
            usage.input_tokens * input_price
            + cache_write * input_price * CACHE_WRITE_MULTIPLIER
            + cache_read * input_price * CACHE_READ_MULTIPLIER
            + usage.output_tokens * output_price
        ) / 1_000_000

    def set_stagehand(self, metrics) -> None:
        """Stagehand's metrics are cumulative for the session, so store the latest snapshot."""
        self.stagehand_prompt = int(metrics.total_prompt_tokens)
        self.stagehand_completion = int(metrics.total_completion_tokens)
        self.stagehand_cached = int(metrics.total_cached_input_tokens)

    @property
    def stagehand_cost(self) -> float:
        return stagehand_cost(self.stagehand_prompt, self.stagehand_completion, self.stagehand_cached)

    @property
    def total_tokens(self) -> int:
        return (
            self.model_input + self.model_cache_write + self.model_cache_read + self.model_output
            + self.stagehand_prompt + self.stagehand_completion
        )

    @property
    def total_cost(self) -> float:
        return self.model_cost + self.stagehand_cost

    def summary(self) -> dict:
        return {
            "brain_models": sorted(self.models_used),
            "model_tokens": {
                "input": self.model_input,
                "cache_write": self.model_cache_write,
                "cache_read": self.model_cache_read,
                "output": self.model_output,
            },
            "stagehand_tokens": {
                "model": LOOKUP_MODEL,
                "prompt": self.stagehand_prompt,
                "completion": self.stagehand_completion,
                "cached_input": self.stagehand_cached,
            },
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": {
                "model": round(self.model_cost, 5),
                "stagehand": round(self.stagehand_cost, 5),
                "total": round(self.total_cost, 5),
            },
        }


def stagehand_cost(prompt: int, completion: int, cached: int) -> float:
    input_price, output_price = _price(LOOKUP_MODEL)
    uncached = max(prompt - cached, 0)
    return (
        uncached * input_price + cached * input_price * CACHE_READ_MULTIPLIER + completion * output_price
    ) / 1_000_000
