"""Tests for ``lexscribe_shared.verify``."""

from __future__ import annotations

from lexscribe_shared.canonicalize import chunk_hash, doc_canonical_hash
from lexscribe_shared.models import Citation
from lexscribe_shared.verify import (
    DictChunkStore,
    StoredChunk,
    verify_citation,
)


def _store_with(text: str, *, doc_text: str | None = None) -> DictChunkStore:
    store = DictChunkStore()
    chunk = StoredChunk(text=text, page=1, char_start=0, char_end=len(text))
    store.put_chunk(doc_id="doc_x", version=1, chunk=chunk)
    if doc_text is not None:
        store.put_doc(doc_id="doc_x", version=1, full_text=doc_text)
    return store


def _citation(text: str, *, doc_text: str | None = None) -> Citation:
    return Citation(
        doc_id="doc_x",
        version=1,
        page=1,
        char_start=0,
        char_end=len(text),
        score=0.9,
        chunk_hash=chunk_hash(text),
        doc_canonical_hash=doc_canonical_hash(doc_text) if doc_text is not None else None,
    )


def test_verify_passes_when_chunk_text_unchanged() -> None:
    text = "Section 1. Effective on the closing date."
    store = _store_with(text)
    citation = _citation(text)
    result = verify_citation(citation, store)
    assert result.ok
    assert result.diff == ""
    assert result.expected_chunk_hash == citation.chunk_hash


def test_verify_fails_when_chunk_text_tampered() -> None:
    original = "Section 1. The agreement is effective."
    tampered = "Section 1. The agreement is voided!!!!"
    assert len(original) == len(tampered), "test fixtures must share coords"
    # The store contains the tampered text *at the same coords* the citation
    # references — this models the case where the doc was edited in place
    # without a new version bump.
    store = DictChunkStore()
    store.put_chunk(
        doc_id="doc_x",
        version=1,
        chunk=StoredChunk(text=tampered, page=1, char_start=0, char_end=len(tampered)),
    )
    citation = _citation(original)  # citation hash refers to original
    result = verify_citation(citation, store)
    assert not result.ok
    assert "citation hash mismatch" in result.diff
    assert citation.chunk_hash in result.diff
    assert result.expected_chunk_hash == chunk_hash(tampered)


def test_verify_fails_when_chunk_missing_from_store() -> None:
    store = DictChunkStore()
    citation = _citation("anything")
    result = verify_citation(citation, store)
    assert not result.ok
    assert "chunk not found in store" in result.diff


def test_verify_fails_when_chunk_hash_field_is_none() -> None:
    """A citation without a recorded chunk_hash cannot be verified."""

    text = "Section 1."
    store = _store_with(text)
    citation = Citation(
        doc_id="doc_x",
        version=1,
        page=1,
        char_start=0,
        char_end=len(text),
        score=0.9,
        # chunk_hash deliberately left None
    )
    result = verify_citation(citation, store)
    assert not result.ok


def test_verify_passes_with_matching_doc_hash() -> None:
    text = "Section 1. Pay parties on the closing date."
    full = "Article I.\n" + text + "\n" + "Article II. Misc."
    store = _store_with(text, doc_text=full)
    citation = _citation(text, doc_text=full)
    result = verify_citation(citation, store)
    assert result.ok
    assert result.expected_doc_hash == doc_canonical_hash(full)


def test_verify_fails_when_doc_hash_drifts() -> None:
    text = "Section 1. Pay parties on the closing date."
    full_old = "Article I. " + text + " Article II. Misc."
    full_new = "Article I. " + text + " Article II. Different."
    # store reflects the *new* doc text but chunk text is unchanged
    store = _store_with(text, doc_text=full_new)
    # citation was generated against the old doc
    citation = _citation(text, doc_text=full_old)
    result = verify_citation(citation, store)
    assert not result.ok
    assert "doc_canonical_hash" in result.diff


def test_verify_doc_hash_check_is_skipped_when_either_side_missing() -> None:
    text = "Section 1. Effective."
    store = _store_with(text)  # no doc_text
    citation = _citation(text, doc_text="anything we want")
    result = verify_citation(citation, store)
    # Without a doc text in the store the doc-level check is non-blocking;
    # the chunk hash still pins the verification.
    assert result.ok


def test_verify_passes_after_canonical_equivalent_whitespace_change() -> None:
    """The whole point of canonicalisation: whitespace-only edits don't break.

    A chunk written with ``"foo  bar"`` (double space) and a chunk later
    rendered as ``"foo bar"`` (single space) hash identically, so the citation
    still verifies. We simulate this by hashing the original-form text and
    storing the renormalised text.
    """

    original = "Termination  Fee:\t$100M"
    rerendered = "Termination Fee: $100M"
    store = _store_with(rerendered)
    # The recorded hash on the citation comes from the original whitespace form
    citation = Citation(
        doc_id="doc_x",
        version=1,
        page=1,
        char_start=0,
        char_end=len(rerendered),
        score=0.9,
        chunk_hash=chunk_hash(original),
    )
    result = verify_citation(citation, store)
    assert result.ok
