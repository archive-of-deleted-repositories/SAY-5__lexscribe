"""In-memory hybrid searcher used by tests, eval, and the API smoke path.

Why in-memory? Two reasons:

1. The eval harness runs the same retrieval logic without Postgres so it can
   gate on retrieval quality in CI.
2. The API path uses pgvector for production but exercises the *same* fusion
   and rerank code by importing from this module.

The DB-backed equivalent lives in ``lexscribe_api.repos.retrieval`` and emits
the same ``ScoredChunk`` shape so callers do not branch.

Sub-millisecond stage timings are recorded into a per-stage HDR histogram
on every call. Bench harnesses and the API metrics endpoint read these
HDR percentiles directly; Prometheus exposition is generated on scrape via
``HdrHistogram.export_prometheus``.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from lexscribe_shared.hdr import HdrHistogram
from rank_bm25 import BM25Okapi

from lexscribe_retrieval.fusion import reciprocal_rank_fusion
from lexscribe_retrieval.rerank import HeuristicReranker, Reranker

# Module-level HDR histograms so every searcher in the process feeds the
# same metric — matches the Prometheus default-registry singleton pattern.
STAGE_HDR: dict[str, HdrHistogram] = {
    "bm25": HdrHistogram(),
    "dense": HdrHistogram(),
    "fusion": HdrHistogram(),
    "rerank": HdrHistogram(),
}


def _record_stage(stage: str, started: float) -> None:
    elapsed_us = int((time.perf_counter() - started) * 1_000_000)
    STAGE_HDR[stage].record(elapsed_us)


@dataclass(frozen=True)
class IndexedChunk:
    chunk_id: str
    text: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class ScoredChunk:
    chunk: IndexedChunk
    score: float


class _Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    denom = (na**0.5) * (nb**0.5) or 1.0
    return dot / denom


class HybridSearcher:
    """BM25 + dense + RRF + rerank. Pure-Python for tests."""

    def __init__(
        self,
        chunks: list[IndexedChunk],
        embedder: _Embedder,
        reranker: Reranker | None = None,
    ) -> None:
        self._chunks = chunks
        self._embedder = embedder
        self._reranker: Reranker = (
            reranker if reranker is not None else HeuristicReranker()  # type: ignore[assignment]
        )
        tokenised = [c.text.lower().split() for c in chunks]
        self._bm25 = BM25Okapi(tokenised) if tokenised else None

    def search(self, query: str, *, k: int = 8, candidate_pool: int = 50) -> list[ScoredChunk]:
        if not self._chunks or self._bm25 is None:
            return []
        # BM25 ranking
        t0 = time.perf_counter()
        bm25_scores = self._bm25.get_scores(query.lower().split())
        bm25_order = sorted(range(len(self._chunks)), key=lambda i: bm25_scores[i], reverse=True)[
            :candidate_pool
        ]
        _record_stage("bm25", t0)
        # Dense ranking
        t0 = time.perf_counter()
        q_emb = self._embedder.embed([query])[0]
        dense_scores = [_cosine(q_emb, c.embedding) for c in self._chunks]
        dense_order = sorted(range(len(self._chunks)), key=lambda i: dense_scores[i], reverse=True)[
            :candidate_pool
        ]
        _record_stage("dense", t0)
        # Fuse
        t0 = time.perf_counter()
        fused = reciprocal_rank_fusion([bm25_order, dense_order])
        top_n = [idx for idx, _ in fused[:candidate_pool]]
        _record_stage("fusion", t0)
        if not top_n:
            return []
        # Rerank top pool down to k
        t0 = time.perf_counter()
        candidates_text = [self._chunks[i].text for i in top_n]
        rerank_scores = self._reranker.rerank(query, candidates_text)
        ranked = sorted(zip(top_n, rerank_scores, strict=False), key=lambda x: x[1], reverse=True)[
            :k
        ]
        _record_stage("rerank", t0)
        return [ScoredChunk(chunk=self._chunks[i], score=float(s)) for i, s in ranked]
