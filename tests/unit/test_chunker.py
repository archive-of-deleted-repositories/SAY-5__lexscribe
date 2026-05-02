from __future__ import annotations

from lexscribe_retrieval.chunker import _split_sentences, chunk_pages


def test_chunks_never_cross_page_boundary() -> None:
    pages = [
        (1, "Section one. Here is the first body. Another sentence."),
        (2, "Section two. New page, new chunk. Final sentence."),
    ]
    chunks = chunk_pages(pages, target_chars=400, overlap_chars=50)
    assert chunks
    pages_seen = {c.page_no for c in chunks}
    assert pages_seen == {1, 2}
    # No chunk text spans both pages
    for c in chunks:
        assert "page" not in c.text.lower() or c.page_no in (1, 2)


def test_chunker_handles_empty_page() -> None:
    chunks = chunk_pages([(1, ""), (2, "Real text here. Another sentence.")])
    assert all(c.page_no == 2 for c in chunks)
    assert chunks


def test_legal_abbreviations_are_not_sentence_terminators() -> None:
    text = "Pursuant to Sec. 12.3 of the Agreement, the parties agree."
    sents = _split_sentences(text)
    # Should be ONE sentence, not split at "Sec."
    assert len(sents) == 1


def test_overlap_keeps_long_clauses_intact() -> None:
    long_clause = "This is sentence " + ". This is sentence ".join(str(i) for i in range(40)) + "."
    chunks = chunk_pages([(1, long_clause)], target_chars=300, overlap_chars=80)
    assert len(chunks) >= 2
    # Each chunk fits its target (with some slack for the last sentence)
    assert all(len(c.text) <= 600 for c in chunks)


def test_offsets_recover_original_text() -> None:
    pages = [(1, "First sentence here. Second one. Third item.")]
    chunks = chunk_pages(pages, target_chars=200, overlap_chars=20)
    src = pages[0][1]
    for c in chunks:
        assert src[c.char_start : c.char_end] == c.text
