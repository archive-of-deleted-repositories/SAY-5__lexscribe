"""Cost accounting. Single place where token counts → USD."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostRates:
    """USD per 1K tokens."""

    in_per_1k: float
    out_per_1k: float
    embed_per_1k: float = 0.0


def turn_cost(*, tokens_in: int, tokens_out: int, rates: CostRates) -> float:
    return (tokens_in / 1000.0) * rates.in_per_1k + (tokens_out / 1000.0) * rates.out_per_1k


def embed_cost(*, tokens: int, rates: CostRates) -> float:
    return (tokens / 1000.0) * rates.embed_per_1k
