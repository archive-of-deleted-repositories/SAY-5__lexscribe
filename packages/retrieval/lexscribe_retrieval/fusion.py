"""Reciprocal Rank Fusion. Standard k=60 from Cormack et al. (2009)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[T]],
    *,
    k: int = 60,
) -> list[tuple[T, float]]:
    """Combine multiple rankings of the same item type into one fused ranking.

    Each ranking is interpreted as best-first. The fused score for an item is
    ``sum(1 / (k + rank_i))`` across rankings where it appears. ``k=60`` is the
    constant from the original paper and works well in practice.
    """

    scores: dict[T, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ordered
