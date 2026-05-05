# EDGAR seed corpus

Five M&A merger agreements pulled from SEC EDGAR full-text filings. The
exhibits cover a spread of drafting eras (2006 → 2023), deal sizes, and
sectors. All are public 8-K Exhibit 2.1 attachments.

## Sources

| doc_id | Filer / target | Form | Filed | URL | Cache |
|---|---|---|---|---|---|
| `doc_msft_atvi_2022` | Microsoft / Activision Blizzard | 8-K Ex-2.1 | 2022-01-19 | <https://www.sec.gov/Archives/edgar/data/718877/000110465922005154/tm223212d3_ex2-1.htm> | `microsoft_activision_2022.html` |
| `doc_pfe_seagen_2023` | Pfizer / Seagen | 8-K Ex-2.1 | 2023-03-13 | <https://www.sec.gov/Archives/edgar/data/78003/000119312523068538/d408093dex21.htm> | `pfizer_seagen_2023.html` |
| `doc_csco_splk_2023` | Cisco Systems / Splunk | 8-K Ex-2.1 | 2023-09-21 | <https://www.sec.gov/Archives/edgar/data/858877/000119312523239165/d464532dex21.htm> | `cisco_splunk_2023.html` |
| `doc_xom_pxd_2023` | ExxonMobil / Pioneer Natural Resources | 8-K Ex-2.1 | 2023-10-11 | <https://www.sec.gov/Archives/edgar/data/34088/000095010323014885/dp201349_ex0201.htm> | `exxon_pioneer_2023.html` |
| `doc_dis_pixar_2006` | Walt Disney / Pixar | 8-K Ex-2.1 | 2006-01-26 | <https://www.sec.gov/Archives/edgar/data/1002114/000119312506012629/dex21.htm> | `disney_pixar_2006.html` |

Retrieval date: 2026-05-05. EDGAR URLs are stable on accession-number paths;
the originals are also reachable via each company's "Filings" tab on
sec.gov.

## How "page" works for these documents

EDGAR delivers these as one continuous HTML document, not paginated PDFs.
The seeder strips HTML, normalises whitespace, then buckets the resulting
plain text into fixed-width windows of `PAGE_CHARS = 4000` characters
(`scripts/seed_edgar.py:paginate`). Citation `(page, char_start, char_end)`
coordinates are *page-relative* and resolve back to the cached HTML via
that same paginator.

This is a study tradeoff: real PDFs would let pages be ground-truth, but
EDGAR exhibits do not have a native PDF rendering and HTML→PDF rasterisation
adds OCR drift. Fixed-window pagination keeps citations reproducible across
runs.

## Rate-limit policy

`seed_edgar.py` sleeps 0.2s between fresh downloads (5 req/s — half EDGAR's
10 req/s ceiling). Cached files are never re-fetched. The User-Agent header
identifies the requester per <https://www.sec.gov/os/accessing-edgar-data>.

## Why these five

- **Microsoft / Activision (2022)**: large-cap tech merger; rich
  Termination Fee structure with both Company and Parent fees that vary
  by date.
- **Pfizer / Seagen (2023)**: pharma; introduces the Reverse Termination
  Fee construct paid by the buyer on antitrust failure.
- **Cisco / Splunk (2023)**: standard 2020s tech merger; clean Section
  numbering useful as a reference for clause taxonomy.
- **ExxonMobil / Pioneer (2023)**: energy sector, all-stock; different
  closing-condition pattern than cash deals.
- **Disney / Pixar (2006)**: pre-Dodd-Frank drafting style, all-stock,
  governed by California law (every other deal here is Delaware) — useful
  for governing-law eval questions.

## Reseeding

```bash
make seed-edgar             # uses cache when present
python scripts/seed_edgar.py --force   # re-downloads everything
```

If your network blocks sec.gov, the cache directory will be incomplete and
the eval harness will skip questions that target the missing documents.
That state is logged but not fatal.
