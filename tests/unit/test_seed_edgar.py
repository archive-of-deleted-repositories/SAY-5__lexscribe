"""Unit tests for the EDGAR seed pure-functional bits.

The network-touching path (``fetch``, ``load_or_fetch``) is not exercised
here — those need either a live EDGAR call or a fixture cache. Pagination
and HTML stripping are pure-functional and worth pinning.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from seed_edgar import PAGE_CHARS, html_to_text, paginate  # noqa: E402


def test_html_to_text_strips_tags_and_decodes_entities() -> None:
    raw = "<p>Hello &amp; <b>world</b></p>"
    assert html_to_text(raw) == "Hello & world"


def test_html_to_text_collapses_whitespace() -> None:
    raw = "<div>foo\n\n\tbar    baz</div>"
    assert html_to_text(raw) == "foo bar baz"


def test_paginate_default_window() -> None:
    body = "x" * (PAGE_CHARS * 2 + 50)
    pages = paginate(body)
    assert len(pages) == 3
    assert pages[0][0] == 1
    assert len(pages[0][1]) == PAGE_CHARS
    assert pages[2][0] == 3
    assert len(pages[2][1]) == 50


def test_paginate_empty_returns_one_blank_page() -> None:
    assert paginate("") == [(1, "")]


def test_paginate_smaller_than_window() -> None:
    pages = paginate("hello world")
    assert pages == [(1, "hello world")]


def test_paginate_custom_window() -> None:
    pages = paginate("abcdefghij", page_chars=3)
    assert pages == [(1, "abc"), (2, "def"), (3, "ghi"), (4, "j")]
