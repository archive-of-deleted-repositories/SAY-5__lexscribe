"""Question-answering service.

This module wires the retrieval package to the provider Protocols. The default
deployment uses a real embedder/LLM; tests inject Fake* implementations and
assert on citation correctness.

The ``default_corpus`` function returns an in-memory demo index so that the API
boots cleanly even without Postgres — it is replaced by the DB-backed corpus
once Alembic migrations have run and seed data exists.
"""

from __future__ import annotations

from functools import lru_cache

from lexscribe_retrieval.search import HybridSearcher, IndexedChunk
from lexscribe_shared.costing import CostRates, turn_cost
from lexscribe_shared.models import Citation, QARequest, QAResponse, Usage
from lexscribe_shared.providers import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    FakeLLMProvider,
    GenerationRequest,
    LLMProvider,
    attach_citations,
)
from lexscribe_shared.settings import get_settings

_DEMO_DOC = "doc_demo000000"
_DEMO_PAGES: list[tuple[int, str]] = [
    (
        1,
        "This Agreement shall terminate automatically upon a Change of Control of "
        "either party, defined as the acquisition of more than fifty percent (50%) "
        "of the outstanding voting securities by a single entity. Notice of any such "
        "event shall be given within five (5) business days.",
    ),
    (
        2,
        "All Intellectual Property created by Contractor in the course of performing "
        "Services hereunder shall vest in Customer upon creation. Contractor hereby "
        "assigns all right, title, and interest, including moral rights to the extent "
        "permitted by law, in such Intellectual Property to Customer.",
    ),
    (
        3,
        "This Agreement shall be governed by and construed in accordance with the laws "
        "of the State of Delaware, without regard to its conflict-of-laws principles. "
        "The parties consent to the exclusive jurisdiction of the state and federal "
        "courts located in Wilmington, Delaware.",
    ),
]


@lru_cache(maxsize=1)
def default_corpus() -> HybridSearcher:
    embedder: EmbeddingProvider = FakeEmbeddingProvider(dim=128)
    chunks: list[IndexedChunk] = []
    for page_no, text in _DEMO_PAGES:
        emb = embedder.embed([text])[0]
        chunks.append(
            IndexedChunk(
                chunk_id=f"{_DEMO_DOC}::p{page_no}",
                text=text,
                embedding=tuple(emb),
            )
        )
    return HybridSearcher(chunks=chunks, embedder=embedder)


def answer_question(
    req: QARequest,
    searcher: HybridSearcher,
    *,
    llm: LLMProvider | None = None,
) -> QAResponse:
    settings = get_settings()
    provider: LLMProvider = llm or FakeLLMProvider(model=settings.generation_model)

    hits = searcher.search(req.question, k=req.k)
    chunks = tuple(h.chunk.text for h in hits)
    citations_pool = [
        Citation(
            doc_id=h.chunk.chunk_id.split("::")[0],
            version=1,
            page=int(h.chunk.chunk_id.split("p")[-1] or 1),
            char_start=0,
            char_end=len(h.chunk.text),
            score=h.score,
        )
        for h in hits
    ]
    gen_req = GenerationRequest(
        system="Answer using only the supplied excerpts. Cite by index.",
        user=req.question,
        chunks=chunks,
        model=settings.generation_model,
    )
    result = provider.generate(gen_req)
    citations = attach_citations(citations_pool, result.citation_indices)
    rates = CostRates(
        in_per_1k=settings.cost_in_per_1k,
        out_per_1k=settings.cost_out_per_1k,
        embed_per_1k=settings.cost_embed_per_1k,
    )
    usage = Usage(
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=turn_cost(tokens_in=result.tokens_in, tokens_out=result.tokens_out, rates=rates),
    )
    return QAResponse(
        answer=result.answer,
        citations=citations,
        usage=usage,
        model_version=result.model,
    )
