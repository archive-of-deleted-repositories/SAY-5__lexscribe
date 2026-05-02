from __future__ import annotations

from lexscribe_shared.costing import CostRates, embed_cost, turn_cost


def test_turn_cost_arithmetic() -> None:
    rates = CostRates(in_per_1k=0.003, out_per_1k=0.015)
    assert abs(turn_cost(tokens_in=1000, tokens_out=2000, rates=rates) - 0.033) < 1e-9


def test_embed_cost_zero_when_rate_zero() -> None:
    rates = CostRates(in_per_1k=0.0, out_per_1k=0.0, embed_per_1k=0.0)
    assert embed_cost(tokens=10_000, rates=rates) == 0.0
