"""Tampered-chunk eval gate.

Drives the full ``answer_question`` path against the demo corpus, captures the
returned citations, then simulates a doc-version drift by tampering with one
chunk's text in a ``DictChunkStore``. ``verify_citation`` must report
``ok=False`` for the tampered citation and ``ok=True`` for the rest.

The test is a smoke at suite scope (small corpus, FakeProvider) — large
corpora live in the EDGAR seed which CI doesn't have HTML for.

Run via the standalone job ``tampered-chunk-eval-smoke`` in CI; locally with
``pytest tests/test_tampered_chunk_eval.py -v``.

The test is hermetic — no DB/Redis/MinIO. It exercises the same code path
production uses (``answer_question`` → ``verify_citation``) on the in-memory
demo corpus.
"""

from __future__ import annotations

from lexscribe_api.qa_service import answer_question, default_corpus
from lexscribe_shared.canonicalize import chunk_hash
from lexscribe_shared.models import QARequest
from lexscribe_shared.verify import DictChunkStore, StoredChunk, verify_citation


def _build_store_from_corpus() -> DictChunkStore:
    """Mirror the demo corpus into a chunk store the verifier can read."""

    from lexscribe_api.qa_service import _DEMO_DOC, _DEMO_PAGES

    store = DictChunkStore()
    for page_no, text in _DEMO_PAGES:
        store.put_chunk(
            doc_id=_DEMO_DOC,
            version=1,
            chunk=StoredChunk(text=text, page=page_no, char_start=0, char_end=len(text)),
        )
    full = "\n".join(t for _, t in _DEMO_PAGES)
    store.put_doc(doc_id=_DEMO_DOC, version=1, full_text=full)
    return store


def test_clean_corpus_verifies_every_returned_citation() -> None:
    searcher = default_corpus()
    resp = answer_question(QARequest(question="What triggers termination?", k=4), searcher)
    assert resp.citations, "demo corpus must return at least one citation"

    store = _build_store_from_corpus()
    for cit in resp.citations:
        assert cit.chunk_hash, "every served citation must carry a chunk_hash"
        result = verify_citation(cit, store)
        assert result.ok, f"clean-corpus verification regressed: {result.diff}"


def test_tampered_chunk_is_caught_by_verify_citation() -> None:
    searcher = default_corpus()
    resp = answer_question(QARequest(question="What law governs the agreement?", k=4), searcher)
    assert resp.citations
    target = resp.citations[0]

    store = _build_store_from_corpus()

    # Simulate a silent doc-version drift: keep coords identical, change bytes.
    # We retrieve the chunk text from the store and mutate it.
    original_chunk = store.fetch(
        doc_id=target.doc_id,
        version=target.version,
        page=target.page,
        char_start=target.char_start,
        char_end=target.char_end,
    )
    assert original_chunk is not None
    tampered_text = original_chunk.text.replace("Delaware", "Mars")
    assert tampered_text != original_chunk.text, "tampering must change the bytes"
    store.put_chunk(
        doc_id=target.doc_id,
        version=target.version,
        chunk=StoredChunk(
            text=tampered_text,
            page=target.page,
            char_start=target.char_start,
            char_end=target.char_end,
        ),
    )

    result = verify_citation(target, store)
    assert not result.ok, "verify-citation must fail on a tampered chunk"
    assert "citation hash mismatch" in result.diff
    # The recorded hash on the citation must still appear in the diff.
    assert target.chunk_hash is not None
    assert target.chunk_hash in result.diff
    # And the recomputed hash must match a fresh hash of the tampered text.
    assert result.expected_chunk_hash == chunk_hash(tampered_text)
