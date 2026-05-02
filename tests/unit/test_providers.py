from __future__ import annotations

from lexscribe_shared.models import Citation
from lexscribe_shared.providers import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    GenerationRequest,
    attach_citations,
)


def test_embeddings_are_deterministic() -> None:
    e = FakeEmbeddingProvider(dim=128)
    a = e.embed(["hello world"])
    b = e.embed(["hello world"])
    assert a == b


def test_embeddings_have_requested_dim() -> None:
    e = FakeEmbeddingProvider(dim=42)
    out = e.embed(["x"])[0]
    assert len(out) == 42


def test_llm_returns_first_chunk_when_chunks_present() -> None:
    llm = FakeLLMProvider()
    req = GenerationRequest(
        system="s",
        user="What is X?",
        chunks=("This is the first chunk.", "Other"),
        model="fake-1",
    )
    out = llm.generate(req)
    assert out.answer.startswith("This is the first")
    assert out.citation_indices == (0,)


def test_llm_handles_empty_chunks_gracefully() -> None:
    llm = FakeLLMProvider()
    req = GenerationRequest(system="s", user="?", chunks=(), model="fake-1")
    out = llm.generate(req)
    assert out.citation_indices == ()
    assert "No relevant" in out.answer


def test_attach_citations_filters_by_index() -> None:
    pool = [
        Citation(doc_id="d1", version=1, page=1, char_start=0, char_end=10, score=0.9),
        Citation(doc_id="d2", version=1, page=2, char_start=0, char_end=10, score=0.5),
    ]
    out = attach_citations(pool, (1,))
    assert [c.doc_id for c in out] == ["d2"]


def test_attach_citations_drops_out_of_range_indices() -> None:
    pool = [Citation(doc_id="d1", version=1, page=1, char_start=0, char_end=10, score=0.9)]
    out = attach_citations(pool, (0, 5, -1))
    assert len(out) == 1
