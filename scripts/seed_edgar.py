"""Seed real M&A merger agreements pulled from SEC EDGAR.

Five 8-K Exhibit 2.1 filings — the operative merger agreements — covering a
spread of drafting styles, deal sizes, and dates. The fetcher caches every
download so re-runs do not re-hit sec.gov.

Pagination is synthetic: SEC delivers these as one long HTML document, not as
paginated PDFs. We strip HTML to plain text, normalise whitespace, then bucket
by a fixed-width window (`PAGE_CHARS`) so every chunk has a stable
``(page, char_start, char_end)`` coordinate that resolves back to the cached
file. The window size is documented in ``data/edgar/MANIFEST.md``.

EDGAR's robots policy requires a User-Agent identifying the requester and
asks for ``<= 10 req/s``. We sleep 0.2s between requests to stay well under.
"""

from __future__ import annotations

import argparse
import html as _html
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "edgar"
USER_AGENT = "Lexscribe Demo saiasish.cnp@gmail.com"
REQUEST_INTERVAL_SECONDS = 0.2  # well under EDGAR's 10 req/s ceiling
PAGE_CHARS = 4000  # synthetic page size for citation coordinates


@dataclass(frozen=True)
class EdgarSource:
    doc_id: str
    title: str
    url: str
    cache_name: str  # filename inside DATA_DIR


_BASE = "https://www.sec.gov/Archives/edgar/data"

SOURCES: tuple[EdgarSource, ...] = (
    EdgarSource(
        doc_id="doc_msft_atvi_2022",
        title="Microsoft / Activision Blizzard — Agreement and Plan of Merger (2022-01-18)",
        url=f"{_BASE}/718877/000110465922005154/tm223212d3_ex2-1.htm",
        cache_name="microsoft_activision_2022.html",
    ),
    EdgarSource(
        doc_id="doc_pfe_seagen_2023",
        title="Pfizer / Seagen — Agreement and Plan of Merger (2023-03-12)",
        url=f"{_BASE}/78003/000119312523068538/d408093dex21.htm",
        cache_name="pfizer_seagen_2023.html",
    ),
    EdgarSource(
        doc_id="doc_csco_splk_2023",
        title="Cisco Systems / Splunk — Agreement and Plan of Merger (2023-09-20)",
        url=f"{_BASE}/858877/000119312523239165/d464532dex21.htm",
        cache_name="cisco_splunk_2023.html",
    ),
    EdgarSource(
        doc_id="doc_xom_pxd_2023",
        title="ExxonMobil / Pioneer Natural Resources — Agreement and Plan of Merger (2023-10-11)",
        url=f"{_BASE}/34088/000095010323014885/dp201349_ex0201.htm",
        cache_name="exxon_pioneer_2023.html",
    ),
    EdgarSource(
        doc_id="doc_dis_pixar_2006",
        title="Walt Disney / Pixar — Agreement and Plan of Merger (2006-01-24)",
        url=f"{_BASE}/1002114/000119312506012629/dex21.htm",
        cache_name="disney_pixar_2006.html",
    ),
)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    """Strip HTML, decode entities, collapse whitespace. Deterministic."""

    stripped = _TAG_RE.sub(" ", raw)
    decoded = _html.unescape(stripped)
    return _WS_RE.sub(" ", decoded).strip()


def paginate(text: str, *, page_chars: int = PAGE_CHARS) -> list[tuple[int, str]]:
    """Bucket plain text into fixed-width pages.

    Returns ``[(page_no, page_text), ...]`` where ``page_no`` starts at 1 and
    ``len(page_text) <= page_chars``. The character offsets used in citations
    are *page-relative*: page 1 chars 0..3999, page 2 chars 0..3999, etc.
    """

    pages: list[tuple[int, str]] = []
    n = len(text)
    page_no = 1
    for start in range(0, n, page_chars):
        pages.append((page_no, text[start : start + page_chars]))
        page_no += 1
    if not pages:
        pages.append((1, ""))
    return pages


def fetch(url: str, *, dest: Path, user_agent: str = USER_AGENT, force: bool = False) -> bytes:
    """Fetch ``url`` to ``dest``, caching on disk. Returns the bytes either way."""

    if dest.exists() and not force:
        return dest.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    dest.write_bytes(body)
    return body


def load_or_fetch(
    src: EdgarSource,
    *,
    data_dir: Path = DATA_DIR,
    sleep_seconds: float = REQUEST_INTERVAL_SECONDS,
) -> str | None:
    """Return cleaned plain text for one EDGAR source, or None on failure."""

    dest = data_dir / src.cache_name
    cached = dest.exists()
    try:
        raw = fetch(src.url, dest=dest)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"  ! skip {src.doc_id}: download failed ({exc})")
        return None
    if not cached and sleep_seconds > 0:
        time.sleep(sleep_seconds)
    try:
        return html_to_text(raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # pragma: no cover — unreachable for well-formed HTML
        print(f"  ! skip {src.doc_id}: parse failed ({exc})")
        return None


@dataclass(frozen=True)
class IngestedDoc:
    doc_id: str
    title: str
    pages: tuple[tuple[int, str], ...]


def ingest_sources(
    sources: tuple[EdgarSource, ...] = SOURCES,
    *,
    data_dir: Path = DATA_DIR,
    sleep_seconds: float = REQUEST_INTERVAL_SECONDS,
) -> list[IngestedDoc]:
    """Fetch+parse all sources, drop any that fail, return the rest."""

    out: list[IngestedDoc] = []
    for src in sources:
        text = load_or_fetch(src, data_dir=data_dir, sleep_seconds=sleep_seconds)
        if text is None:
            continue
        pages = tuple(paginate(text))
        out.append(IngestedDoc(doc_id=src.doc_id, title=src.title, pages=pages))
    return out


def build_corpus(
    sources: tuple[EdgarSource, ...] = SOURCES,
    *,
    data_dir: Path = DATA_DIR,
    embed_dim: int = 128,
):
    """Build a HybridSearcher over the EDGAR corpus.

    Reuses the same chunk → embed path the synthetic seed runs through, so
    the eval harness sees one shape regardless of corpus.
    """

    # Imports kept lazy so the seed script is import-safe in environments
    # where the retrieval extras are not installed (e.g. early CI stages).
    from lexscribe_retrieval.chunker import chunk_pages
    from lexscribe_retrieval.search import HybridSearcher, IndexedChunk
    from lexscribe_shared.providers import FakeEmbeddingProvider

    docs = ingest_sources(sources, data_dir=data_dir, sleep_seconds=REQUEST_INTERVAL_SECONDS)
    embedder = FakeEmbeddingProvider(dim=embed_dim)
    indexed: list[IndexedChunk] = []
    for d in docs:
        chunks = chunk_pages(list(d.pages), target_chars=1200, overlap_chars=150)
        if not chunks:
            continue
        texts = [c.text for c in chunks]
        vecs = embedder.embed(texts)
        for c, vec in zip(chunks, vecs, strict=True):
            indexed.append(
                IndexedChunk(
                    chunk_id=f"{d.doc_id}::p{c.page_no}::{c.char_start}-{c.char_end}",
                    text=c.text,
                    embedding=tuple(vec),
                )
            )
    return HybridSearcher(chunks=indexed, embedder=embedder), docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Lexscribe with real EDGAR contracts.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="cache directory (default: scripts/data/edgar/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even if a cached file exists",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="dry-run; print one page per ingested doc and exit",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"# seed_edgar — caching to {data_dir}")
    docs = []
    for src in SOURCES:
        dest = data_dir / src.cache_name
        if args.force and dest.exists():
            dest.unlink()
        text = load_or_fetch(src, data_dir=data_dir)
        if text is None:
            continue
        pages = paginate(text)
        docs.append((src, pages))
        print(f"  ok {src.doc_id} ({len(text):>7} chars, {len(pages):>3} pages)")

    if args.print and docs:
        src, pages = docs[0]
        print(f"\n--- {src.doc_id} page 1 (first 400 chars) ---")
        print(pages[0][1][:400])
        return

    print(f"# ingested {len(docs)}/{len(SOURCES)} documents")


if __name__ == "__main__":
    main()
