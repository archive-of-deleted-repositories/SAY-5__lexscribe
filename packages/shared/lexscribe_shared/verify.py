"""Citation verification.

A citation is verifiable when its ``chunk_hash`` re-derived from the chunk
text currently in the store matches the hash recorded in the citation. If it
does, the answer's evidence is bit-for-bit identical (up to canonical form)
to what the user uploaded.

The chunk store is a thin Protocol so the verifier can run against:

* a unit-test dict (the default in tests),
* a Postgres-backed store (in production / integration tests),
* a JSON cache file (the CLI's offline mode for archived runs).

This module is provider/DB free; only ``hashlib`` + the canonicaliser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lexscribe_shared.canonicalize import chunk_hash, doc_canonical_hash
from lexscribe_shared.models import Citation


@dataclass(frozen=True)
class StoredChunk:
    """The minimal chunk record the verifier needs from any store."""

    text: str
    page: int
    char_start: int
    char_end: int


class ChunkStore(Protocol):
    """Lookup interface. Returns the chunk text at the given coordinates,
    or ``None`` if the chunk is not in the store."""

    def fetch(
        self, *, doc_id: str, version: int, page: int, char_start: int, char_end: int
    ) -> StoredChunk | None: ...

    def fetch_doc_text(self, *, doc_id: str, version: int) -> str | None: ...


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    """True iff the citation's ``chunk_hash`` matched the recomputed hash."""

    citation: Citation
    """The input citation, echoed for caller convenience."""

    expected_chunk_hash: str | None
    """The chunk hash derived from the store's current text for these coords."""

    expected_doc_hash: str | None
    """The doc hash derived from the store's current full text, if available."""

    diff: str
    """Markdown-shaped diff. Empty string when ``ok`` is True."""


def _markdown_diff(citation: Citation, expected_chunk: str | None, expected_doc: str | None) -> str:
    lines = ["## citation hash mismatch", ""]
    lines.append(f"- doc_id: `{citation.doc_id}`")
    lines.append(f"- version: `{citation.version}`")
    lines.append(
        f"- coords: page=`{citation.page}` " f"chars=`[{citation.char_start},{citation.char_end})`"
    )
    lines.append("")
    lines.append("### chunk_hash")
    lines.append(f"- recorded:  `{citation.chunk_hash}`")
    lines.append(f"- recomputed:`{expected_chunk}`")
    if citation.doc_canonical_hash is not None or expected_doc is not None:
        lines.append("")
        lines.append("### doc_canonical_hash")
        lines.append(f"- recorded:  `{citation.doc_canonical_hash}`")
        lines.append(f"- recomputed:`{expected_doc}`")
    return "\n".join(lines)


def verify_citation(citation: Citation, store: ChunkStore) -> VerifyResult:
    """Look up the chunk and, when available, the doc text; recompute hashes;
    compare. Mismatches return ``ok=False`` with a Markdown diff.

    The verifier is *strict on chunk_hash*: a missing recorded ``chunk_hash``
    fails verification — the whole point of v3 is that every served citation
    carries one. ``doc_canonical_hash`` is checked when both sides are
    populated; otherwise that line is omitted from the diff.
    """

    chunk_record = store.fetch(
        doc_id=citation.doc_id,
        version=citation.version,
        page=citation.page,
        char_start=citation.char_start,
        char_end=citation.char_end,
    )
    if chunk_record is None:
        diff = _markdown_diff(citation, None, None)
        return VerifyResult(
            ok=False,
            citation=citation,
            expected_chunk_hash=None,
            expected_doc_hash=None,
            diff=diff + "\n\n_chunk not found in store_",
        )

    expected_chunk = chunk_hash(chunk_record.text)
    expected_doc: str | None = None
    full_text = store.fetch_doc_text(doc_id=citation.doc_id, version=citation.version)
    if full_text is not None:
        expected_doc = doc_canonical_hash(full_text)

    chunk_ok = citation.chunk_hash is not None and expected_chunk == citation.chunk_hash
    doc_ok = (
        # If the citation didn't record one OR the store can't supply one,
        # the doc-level check is non-blocking.
        citation.doc_canonical_hash is None
        or expected_doc is None
        or expected_doc == citation.doc_canonical_hash
    )
    ok = chunk_ok and doc_ok

    if ok:
        return VerifyResult(
            ok=True,
            citation=citation,
            expected_chunk_hash=expected_chunk,
            expected_doc_hash=expected_doc,
            diff="",
        )

    return VerifyResult(
        ok=False,
        citation=citation,
        expected_chunk_hash=expected_chunk,
        expected_doc_hash=expected_doc,
        diff=_markdown_diff(citation, expected_chunk, expected_doc),
    )


# ---- A simple in-memory store for tests + CLI offline mode ---- #


class DictChunkStore:
    """In-memory chunk store keyed on the citation tuple."""

    def __init__(self) -> None:
        self._chunks: dict[tuple[str, int, int, int, int], StoredChunk] = {}
        self._docs: dict[tuple[str, int], str] = {}

    def put_chunk(self, *, doc_id: str, version: int, chunk: StoredChunk) -> None:
        key = (doc_id, version, chunk.page, chunk.char_start, chunk.char_end)
        self._chunks[key] = chunk

    def put_doc(self, *, doc_id: str, version: int, full_text: str) -> None:
        self._docs[(doc_id, version)] = full_text

    def fetch(
        self, *, doc_id: str, version: int, page: int, char_start: int, char_end: int
    ) -> StoredChunk | None:
        return self._chunks.get((doc_id, version, page, char_start, char_end))

    def fetch_doc_text(self, *, doc_id: str, version: int) -> str | None:
        return self._docs.get((doc_id, version))
