from __future__ import annotations

from lexscribe_retrieval.rerank import HeuristicReranker


def test_reranker_returns_zero_for_empty_query() -> None:
    r = HeuristicReranker()
    scores = r.rerank("", ["some text", "other"])
    assert scores == [0.0, 0.0]


def test_reranker_ranks_overlapping_chunk_highest() -> None:
    r = HeuristicReranker()
    scores = r.rerank(
        "What is the governing law of the agreement?",
        [
            "This agreement shall be governing law in Delaware.",
            "Random unrelated text about the moon.",
            "Another snippet about whales.",
        ],
    )
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_reranker_handles_empty_candidate() -> None:
    r = HeuristicReranker()
    scores = r.rerank("anything", ["", "real text here"])
    assert scores[0] == 0.0
