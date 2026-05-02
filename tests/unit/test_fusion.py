from __future__ import annotations

from lexscribe_retrieval.fusion import reciprocal_rank_fusion


def test_rrf_prefers_items_in_both_rankings() -> None:
    a = ["x", "y", "z"]
    b = ["y", "x", "w"]
    fused = reciprocal_rank_fusion([a, b])
    items = [item for item, _ in fused]
    # y appears at rank 1 in b and rank 2 in a → should outrank z which is only in a
    assert items[0] in {"x", "y"}
    assert "z" in items
    assert items.index("z") > items.index("y")


def test_rrf_empty_input_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []


def test_rrf_scores_decrease_monotonically() -> None:
    a = list("abcdef")
    b = list("fedcba")
    fused = reciprocal_rank_fusion([a, b])
    scores = [s for _, s in fused]
    assert scores == sorted(scores, reverse=True)
