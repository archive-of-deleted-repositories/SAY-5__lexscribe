from __future__ import annotations

from lexscribe_retrieval.search import HybridSearcher, IndexedChunk
from lexscribe_shared.providers import FakeEmbeddingProvider


def _build_index(texts: list[str]) -> HybridSearcher:
    embedder = FakeEmbeddingProvider(dim=64)
    embs = embedder.embed(texts)
    chunks = [
        IndexedChunk(chunk_id=f"c{i}", text=t, embedding=tuple(e))
        for i, (t, e) in enumerate(zip(texts, embs, strict=False))
    ]
    return HybridSearcher(chunks, embedder)


def test_empty_index_returns_no_hits() -> None:
    searcher = HybridSearcher([], FakeEmbeddingProvider(dim=64))
    assert searcher.search("anything") == []


def test_search_returns_relevant_chunk_first() -> None:
    searcher = _build_index(
        [
            "The capital of France is Paris.",
            "The mitochondria is the powerhouse of the cell.",
            "Bananas grow in tropical climates.",
        ]
    )
    hits = searcher.search("What is the capital of France?", k=3)
    assert hits
    assert "Paris" in hits[0].chunk.text


def test_k_limits_returned_results() -> None:
    searcher = _build_index([f"chunk number {i} about widgets" for i in range(20)])
    hits = searcher.search("widgets", k=4)
    assert len(hits) == 4
