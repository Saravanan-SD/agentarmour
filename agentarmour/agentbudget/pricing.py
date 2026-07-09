# agentarmour/agentbudget/pricing.py
from .config import ModelPrice


class UnknownModelError(KeyError):
    """Raised when a model has no price in the config."""


def price_for(model: str, prices: dict[str, ModelPrice]) -> ModelPrice:
    if model not in prices:
        raise UnknownModelError(model)
    return prices[model]


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    prices: dict[str, ModelPrice],
) -> float:
    price = price_for(model, prices)
    inp = input_tokens / 1_000_000 * price.input_per_million
    out = output_tokens / 1_000_000 * price.output_per_million
    return inp + out