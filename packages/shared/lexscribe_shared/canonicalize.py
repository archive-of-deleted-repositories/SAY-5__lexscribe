"""Canonical-form text utilities for content-addressed citations.

Two hashes are persisted at ingest time and travel with every citation:

* ``doc_canonical_hash`` — sha256 of the canonical form of the *whole* document
  text. Pins the citation to the exact doc-version contents the user uploaded.
* ``chunk_hash``         — sha256 of the canonical form of a single chunk's
  text. Pins each citation span to its retrieved-chunk contents.

Canonicalisation is deliberately small: ``unicodedata.NFKC`` to flatten
compatibility forms (so "ﬃ" → "ffi"), lowercase, then collapse all whitespace
to single spaces and strip. Lower-case is part of canonical form because legal
contracts often differ on display casing for headings/all-caps terms across
versions of the same agreement.

Canonical form is one-way for verification: the hash is reproducible from the
raw chunk text the worker stored, but the canonicalised string is *not* meant
to be reversed back to the source text. ``verify_citation`` re-canonicalises a
chunk fetched from the DB and compares hashes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def canonicalize_text(text: str) -> str:
    """Return the canonical form used for hashing.

    Pure function. Same input always returns the same output.
    """

    nfkc = unicodedata.normalize("NFKC", text)
    lowered = nfkc.lower()
    collapsed = _WHITESPACE_RE.sub(" ", lowered).strip()
    return collapsed


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def chunk_hash(text: str) -> str:
    """sha256 over the canonical form of a chunk's text. 64-char hex."""

    return _sha256_hex(canonicalize_text(text))


def doc_canonical_hash(full_text: str) -> str:
    """sha256 over the canonical form of a whole document's text. 64-char hex."""

    return _sha256_hex(canonicalize_text(full_text))
