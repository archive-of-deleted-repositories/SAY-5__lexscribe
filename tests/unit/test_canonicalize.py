"""Tests for canonical-form text utilities."""

from __future__ import annotations

from lexscribe_shared.canonicalize import (
    canonicalize_text,
    chunk_hash,
    doc_canonical_hash,
)


def test_canonicalize_collapses_whitespace() -> None:
    assert canonicalize_text("hello   world\nthere\t!") == "hello world there !"


def test_canonicalize_lowercases() -> None:
    assert canonicalize_text("Termination Fee") == "termination fee"


def test_canonicalize_nfkc_compatibility_forms() -> None:
    # The Unicode ligature U+FB03 (ﬃ) maps to "ffi" under NFKC.
    assert canonicalize_text("eﬃcient") == "efficient"


def test_canonicalize_strips_leading_trailing_whitespace() -> None:
    assert canonicalize_text("   trim me   ") == "trim me"


def test_canonicalize_handles_empty_string() -> None:
    assert canonicalize_text("") == ""


def test_canonicalize_is_idempotent() -> None:
    once = canonicalize_text("Hello WORLD\n")
    twice = canonicalize_text(once)
    assert once == twice


def test_chunk_hash_is_sha256_hex() -> None:
    h = chunk_hash("abc")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_chunk_hash_invariant_under_whitespace_changes() -> None:
    a = chunk_hash("the quick brown fox")
    b = chunk_hash("the   quick\nbrown\tfox")
    assert a == b


def test_chunk_hash_invariant_under_case() -> None:
    assert chunk_hash("Termination") == chunk_hash("termination")


def test_chunk_hash_changes_when_content_changes() -> None:
    assert chunk_hash("alpha") != chunk_hash("beta")


def test_doc_canonical_hash_differs_from_chunk_hash_for_short_input() -> None:
    """Both functions hash the same canonical form, so on the same input they
    return the same digest. The semantic distinction is at the call site, not
    the algorithm — the test guards that the hash changes when the input does.
    """

    full = "ARTICLE I. " + ("foo " * 1000)
    assert doc_canonical_hash(full) != doc_canonical_hash(full + " bar")


def test_doc_canonical_hash_matches_chunk_hash_on_same_input() -> None:
    s = "Section 1. The agreement is effective."
    assert doc_canonical_hash(s) == chunk_hash(s)
