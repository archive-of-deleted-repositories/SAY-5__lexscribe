"""Page-aware sentence chunker.

Two non-obvious choices:

* Chunks never cross a page boundary. This keeps the page number in every
  citation honest. The cost is the occasional short chunk at end-of-page.
* Sentences are detected with a tolerant regex — full NLTK is overkill for
  contract prose and ships 100MB of model files. Edge cases (numbered lists,
  "Sec. 12.3.4" abbreviations) are handled with a small abbreviation set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

ABBREV = {"sec.", "no.", "art.", "para.", "inc.", "co.", "ltd.", "v.", "vs.", "e.g.", "i.e."}
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"\[])")


@dataclass(frozen=True)
class Chunk:
    """A retrievable text chunk anchored back to its source page."""

    page_no: int
    char_start: int
    char_end: int
    text: str


def _split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Yield ``(start, end, sentence)``. Robust to common legal abbreviations."""

    if not text.strip():
        return []
    candidates = list(_SENT_RE.finditer(text))
    boundaries: list[int] = [0]
    for m in candidates:
        prev = text[: m.start()].rstrip()
        last_word = prev.split()[-1].lower() if prev.split() else ""
        if last_word in ABBREV:
            continue
        boundaries.append(m.end())
    boundaries.append(len(text))
    out: list[tuple[int, int, str]] = []
    for a, b in pairwise(boundaries):
        s = text[a:b].strip()
        if s:
            # Recompute trim offset so char positions stay accurate
            start = a + (len(text[a:b]) - len(text[a:b].lstrip()))
            end = start + len(s)
            out.append((start, end, s))
    return out


def chunk_pages(
    pages: list[tuple[int, str]],
    *,
    target_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[Chunk]:
    """Chunk a list of ``(page_no, text)`` into bounded, overlapping chunks.

    Overlap exists so a span of interest that straddles a chunk boundary still
    appears whole in at least one chunk — without it, recall drops on long
    clauses.
    """

    out: list[Chunk] = []
    for page_no, text in pages:
        sents = _split_sentences(text)
        if not sents:
            continue
        i = 0
        while i < len(sents):
            buf_start = sents[i][0]
            buf_end = sents[i][1]
            j = i
            while j + 1 < len(sents) and (sents[j + 1][1] - buf_start) <= target_chars:
                j += 1
                buf_end = sents[j][1]
            chunk_text = text[buf_start:buf_end].strip()
            if chunk_text:
                out.append(Chunk(page_no, buf_start, buf_end, chunk_text))
            if j >= len(sents) - 1:
                break
            # Walk back by overlap to seed next chunk
            advance_to = j + 1
            target_back = max(buf_end - overlap_chars, buf_start)
            while advance_to > i + 1 and sents[advance_to - 1][0] >= target_back:
                advance_to -= 1
            i = advance_to
    return out
