# Bench harness

Measures the chunk → embed → search → answer pipeline at three scales and
prints a columnar latency report. The artifact in `bench/results/<ts>.json`
is the source of truth for any numbers quoted in `README.md`.

## What is measured

| Stage          | Where it runs                                                     |
|----------------|--------------------------------------------------------------------|
| `parse`        | per-doc time to construct a synthetic contract via `synth_contract` |
| `chunk`        | per-doc time inside `lexscribe_retrieval.chunker.chunk_pages`     |
| `embed`        | per-doc batched call to `FakeEmbeddingProvider.embed`             |
| `classify`     | per-doc keyword classifier (mirrors `classify_spans` in the worker) |
| `bm25`         | per-query `BM25Okapi.get_scores` + sort                           |
| `dense`        | per-query embedder call + cosine over all chunks                  |
| `fusion`       | per-query reciprocal rank fusion                                  |
| `rerank`       | per-query `HeuristicReranker.rerank` over top-50 candidates       |
| `e2e_qa`       | wall-clock of the full Q&A turn (retrieval + provider + accounting)|
| `cost_per_turn`| `turn_cost(...)` against `FakeProvider` token counts              |

## What is held constant

* Provider: `FakeLLMProvider` and `FakeEmbeddingProvider(dim=128)`. No
  network. No real LLM cost.
* Embedding dimension: 128.
* Chunker: `target_chars=1200`, `overlap_chars=150`.
* Reranker: `HeuristicReranker` (lexical overlap, no model load).
* RNG seed: `1234` (override via `--seed`).
* Synthetic doc shape: 6 pages each from `scripts.seed.synth_contract`.

## What varies

`--scale` switches three preset workloads:

| Scale  | Docs  | Queries |
|--------|------:|--------:|
| small  |   10  |     50  |
| medium |  100  |    200  |
| large  | 1000  |    500  |

## Why these scales

The harness has to stay green in CI in seconds, so `small` is the default
and the size that any quoted README number comes from. `medium` is the
realistic local-laptop sanity check before a release. `large` exists to
catch superlinear behaviour in the BM25 + dense path; with 1k synthetic
contracts you should still see sub-100ms P95 retrieval — anything worse
points at an algorithmic regression.

## What the numbers do *not* mean

* This is **not** production cluster behaviour. There is no Postgres
  round-trip, no pgvector index, no queueing, no Celery scheduling, no
  network jitter, no OS page-cache cold start.
* The cost-per-turn line is `FakeProvider` token counts run through
  `turn_cost` with the configured rate card. It exercises the accounting
  code path; it does not measure live LLM cost. Live cost is BYOK and
  outside this harness.
* `parse` here constructs a synthetic in-memory contract; the real PDF
  parse stage in `lexscribe_worker.tasks.parse_pdf` is dominated by I/O
  and OCR, which this harness intentionally does not exercise.

## Running

```bash
make bench                  # small (default)
make bench SCALE=medium
make bench SCALE=large

python bench/bench.py --scale small --no-write   # report only, no artifact
```

The columnar report goes to stdout. A JSON artifact lands in
`bench/results/<UTC-timestamp>_<scale>.json` unless `--no-write` is set.

## Reproducing the README numbers

The numbers in the top-level `README.md` "Bench" section come from the most
recent committed artifact in `bench/results/`. To refresh:

```bash
make bench                                   # writes a new artifact
ls -t bench/results/*.json | head -1         # latest
```

Update the README "Bench" section to point at the new artifact and quote
the matching numbers.
