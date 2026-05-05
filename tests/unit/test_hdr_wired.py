"""End-to-end check: HDR-backed retrieval metrics flow through /metrics."""

from __future__ import annotations

from fastapi.testclient import TestClient
from lexscribe_api.main import app
from lexscribe_retrieval.search import STAGE_HDR, HybridSearcher, IndexedChunk
from lexscribe_shared.providers import FakeEmbeddingProvider


def _build_searcher() -> HybridSearcher:
    embedder = FakeEmbeddingProvider(dim=64)
    chunks = []
    for i, text in enumerate(
        [
            "Change of Control means the acquisition of a majority interest.",
            "Intellectual Property created hereunder vests in the Customer.",
            "This Agreement is governed by Delaware law.",
        ]
    ):
        emb = embedder.embed([text])[0]
        chunks.append(IndexedChunk(chunk_id=f"c{i}", text=text, embedding=tuple(emb)))
    return HybridSearcher(chunks=chunks, embedder=embedder)


def test_search_populates_hdr_stages() -> None:
    for hdr in STAGE_HDR.values():
        hdr.reset()
    searcher = _build_searcher()
    for _ in range(20):
        searcher.search("Who owns intellectual property?", k=2, candidate_pool=10)
    for stage in ("bm25", "dense", "fusion", "rerank"):
        assert STAGE_HDR[stage].total_count() == 20, stage


def test_metrics_endpoint_exposes_hdr_blocks() -> None:
    for hdr in STAGE_HDR.values():
        hdr.reset()
    searcher = _build_searcher()
    for _ in range(5):
        searcher.search("change of control?", k=2, candidate_pool=10)

    with TestClient(app) as client:
        resp = client.get("/metrics/")
        assert resp.status_code == 200
        body = resp.text
        # HDR exposition for each retrieval stage should be present.
        for stage in ("bm25", "dense", "fusion", "rerank"):
            assert f"lexscribe_retrieve_{stage}_seconds_count" in body, stage
            assert f"lexscribe_retrieve_{stage}_seconds_bucket" in body, stage
        # Original Prometheus QA-latency histogram is still there.
        assert "lexscribe_qa_latency_seconds" in body
