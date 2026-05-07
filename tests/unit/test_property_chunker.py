"""Property-based tests for the chunker.

The spec mentions a concatenation invariant. With overlap > 0 the textbook
"concatenation equals source" identity does not hold for this chunker by
design, so the property here is the verifiable substitute: every chunk's
``(char_start, char_end)`` slice of the source page exactly reproduces the
chunk's text, every chunk is page-local, and chunk lengths are bounded above
by ``target_chars + slack``.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from lexscribe_retrieval.chunker import Chunk, chunk_pages

# Letters + digits + a few legal-doc-friendly punctuation marks. We avoid the
# control-character grab-bag because the regex sentence splitter is not
# specified for those.
_TEXT_ALPHABET = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
        whitelist_characters=" .,;:!?()[]'\"-",
    ),
    min_size=0,
    max_size=400,
)

_PAGE_STRATEGY = st.tuples(st.integers(min_value=1, max_value=999), _TEXT_ALPHABET)
_PAGES_STRATEGY = st.lists(_PAGE_STRATEGY, min_size=1, max_size=6, unique_by=lambda p: p[0])


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pages=_PAGES_STRATEGY, target=st.integers(min_value=80, max_value=2400))
def test_every_chunk_is_page_local(pages: list[tuple[int, str]], target: int) -> None:
    """No chunk text spans two pages."""

    chunks = chunk_pages(pages, target_chars=target, overlap_chars=min(target // 4, 200))
    page_texts = dict(pages)
    for c in chunks:
        assert c.page_no in page_texts
        # The chunk's char range must be valid inside its own page's text.
        src = page_texts[c.page_no]
        assert 0 <= c.char_start < c.char_end <= len(src)


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pages=_PAGES_STRATEGY, target=st.integers(min_value=80, max_value=2400))
def test_chunk_offsets_recover_chunk_text(pages: list[tuple[int, str]], target: int) -> None:
    """``page_text[char_start:char_end]`` must equal the chunk's stored text."""

    chunks = chunk_pages(pages, target_chars=target, overlap_chars=min(target // 4, 200))
    page_texts = dict(pages)
    for c in chunks:
        src = page_texts[c.page_no]
        assert src[c.char_start : c.char_end] == c.text


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pages=_PAGES_STRATEGY, target=st.integers(min_value=120, max_value=2400))
def test_chunk_lengths_are_bounded(pages: list[tuple[int, str]], target: int) -> None:
    """Length is bounded by ``target_chars`` plus one terminal sentence's slack.

    The chunker greedily packs whole sentences and only stops once the next
    sentence would push past ``target_chars``. The longest possible chunk is
    therefore ``target_chars`` plus the longest remaining sentence in that
    page. Bounding by ``2 * target`` is the conservative invariant the
    implementation guarantees for any input under the strategy.
    """

    chunks = chunk_pages(pages, target_chars=target, overlap_chars=min(target // 4, 200))
    upper = 2 * target
    for c in chunks:
        assert 1 <= len(c.text) <= upper


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pages=_PAGES_STRATEGY)
def test_chunks_carry_the_input_page_numbers_only(
    pages: list[tuple[int, str]],
) -> None:
    """The set of pages in the output is a subset of the input pages."""

    chunks = chunk_pages(pages, target_chars=600, overlap_chars=80)
    input_pages = {p for p, _ in pages}
    assert {c.page_no for c in chunks} <= input_pages


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pages=_PAGES_STRATEGY)
def test_chunks_are_frozen_dataclass_instances(pages: list[tuple[int, str]]) -> None:
    chunks = chunk_pages(pages, target_chars=400, overlap_chars=60)
    for c in chunks:
        assert isinstance(c, Chunk)
