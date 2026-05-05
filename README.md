# Lexscribe

A small M&A diligence service: upload contracts, get answers with span-level
citations back to the exact page and character range. Hybrid retrieval (BM25 +
pgvector dense + cross-encoder rerank), provider-agnostic generation, and an
eval harness that gates retrieval and faithfulness in CI.

## What this studies

* How to ship a RAG system whose **citations are first-class** rather than
  decorative — every answer is constrained at generation time to cite indices
  from the retrieved set, so an answer can never invent a source.
* How to keep a long-running ingest pipeline honest under partial failure: per
  stage idempotency keys, per chunk transactional commits, a dead-letter table
  with a replay CLI, and exponential backoff with jitter on a fixed schedule.
* How to make the whole system testable without paying for an LLM: every
  generation/embedding call goes through a `Provider` Protocol with a
  deterministic `FakeProvider` that runs in CI.

## Baseline results

| suite          | n  | precision@1 | recall@5 | faithfulness | refusal | p95_latency_s | cost_usd_avg |
|----------------|----|------------:|---------:|-------------:|--------:|--------------:|-------------:|
| mna_v1         | 10 | 1.00        | 1.00     | 0.00         | 0.00    | 0.0003        | 0.000953     |
| mna_real_v1    | 10 | 0.50        | 0.50     | 0.00         | 0.00    | 0.0188        | 0.004830     |

FakeProvider hermetic baseline, M-series Mac. Source artifacts in
`eval/baselines/` (`mna_v1_fake.json`, `mna_real_v1_fake.json`).

The `mna_v1` suite runs over the synthetic three-page demo corpus where
each clause type appears exactly once, so the BM25 + dense retriever
trivially scores 1.00. The `mna_real_v1` suite is the harder, honest
number: ten hand-written diligence questions over five real EDGAR merger
agreements (Microsoft/Activision, Pfizer/Seagen, Cisco/Splunk,
ExxonMobil/Pioneer, Disney/Pixar) where every contract talks about
"termination fee" and "governing law" so lexical retrieval has to
disambiguate by company name. The 0.50 figures are the ceiling for the
small fused BM25+dense+heuristic-rerank stack on this corpus — improving
them is a stack-tuning exercise the eval harness is set up to gate.

`faithfulness` is `0.00` by construction because the FakeProvider returns
canned answers that do not echo retrieved text — the rubric requires word
overlap with citations. Live-LLM numbers require BYOK; see the "Live Eval
(BYOK)" section below. Run `make bench-eval` (synthetic) or
`make seed-edgar && lexscribe eval run --suite mna_real_v1 --provider fake
--output eval/runs/$(date -u +%Y%m%dT%H%M%SZ).json` (real corpus) to
reproduce.

## Layout

```
.
├── packages/
│   ├── shared/          # Pydantic models, errors, settings, OTel, providers, costing
│   ├── retrieval/       # chunker, BM25+dense fusion, reranker, hybrid searcher
│   ├── eval/            # CLI, suites/, metrics, runner
│   └── clients/python/  # hand-written httpx client
├── services/
│   ├── api/             # FastAPI app, routers, qa_service, openapi.yaml
│   └── ingest-worker/   # Celery DAG: parse → chunk → embed → classify
├── alembic/             # one migration; up + down both implemented
├── scripts/
│   ├── seed.py          # Faker-driven synthetic contracts
│   ├── seed_edgar.py    # 5 real EDGAR merger agreements (cached)
│   └── data/edgar/      # MANIFEST.md + cached HTML (gitignored)
├── tests/               # unit + integration (gated) + contract
├── eval/
│   ├── baselines/       # committed FakeProvider baseline artifacts
│   ├── golden/          # hand-written real-corpus suites (mna_real_v1)
│   └── runs/            # local eval runs (gitignored)
├── bench/               # multi-scale bench harness + README + results/
├── infra/               # otel-collector config + Grafana dashboard JSON
├── Dockerfile.api / Dockerfile.worker
├── docker-compose.yml
├── bench.sh             # legacy single-script benchmark
└── pyproject.toml
```

## Modules

| Path | Responsibility |
|---|---|
| `lexscribe_shared.models` | Wire models (`QARequest`, `QAResponse`, `Citation`, `ClauseType`, …) |
| `lexscribe_shared.errors` | Typed exception hierarchy + `ErrorEnvelope` |
| `lexscribe_shared.cursor` | Opaque base64 cursor codec for keyset pagination |
| `lexscribe_shared.providers` | `LLMProvider` / `EmbeddingProvider` Protocols + `FakeProvider` |
| `lexscribe_shared.retry` | Canonical backoff schedule (`1, 4, 16, 64s` ±20% jitter) |
| `lexscribe_retrieval.chunker` | Page-aware sentence chunker that never crosses a page boundary |
| `lexscribe_retrieval.fusion` | Reciprocal Rank Fusion (`k=60`) |
| `lexscribe_retrieval.rerank` | Cross-encoder Protocol + heuristic reranker for tests |
| `lexscribe_retrieval.search` | `HybridSearcher`: BM25 + dense + RRF + rerank |
| `lexscribe_api.qa_service` | Glues retrieval → provider → response with cost accounting |
| `lexscribe_worker.tasks` | Celery DAG; `run_pipeline_sync` for in-process tests/bench |
| `lexscribe_eval.runner` | Loads YAML suites, runs them, scores, persists JSON |
| `lexscribe_eval.metrics` | precision@1, recall@5, faithfulness, refusal, P95, cost |

## Quickstart

```bash
make install                 # creates .venv and installs in editable mode
make lint typecheck test     # ~5s on a laptop
make bench                   # FakeProvider ingest+QA loop, prints percentiles
lexscribe eval run --suite mna_v1 --provider fake --output runs/$(date +%s).json
```

Bringing up the local stack (postgres+pgvector, redis, minio, otel-collector):

```bash
docker compose up -d
make migrate                 # alembic upgrade head
make seed                    # synthetic contracts
make dev                     # uvicorn on :8080
```

## Demo — real EDGAR contracts

Five 8-K Exhibit 2.1 merger agreements (Microsoft/Activision,
Pfizer/Seagen, Cisco/Splunk, ExxonMobil/Pioneer, Disney/Pixar) ingest
through the same chunk → embed → classify path as the synthetic seed.
Source URLs and pagination notes are in
[scripts/data/edgar/MANIFEST.md](scripts/data/edgar/MANIFEST.md).

```bash
make seed-edgar              # caches under scripts/data/edgar/
lexscribe eval run \
  --suite mna_real_v1 \
  --provider fake \
  --output eval/baselines/mna_real_v1_fake.json
```

Ten hand-written diligence questions live in
[eval/golden/mna_real_v1.yaml](eval/golden/mna_real_v1.yaml). Each
question pins the expected document and a verified `(page, char_start,
char_end)` citation range, so the retrieval gate has ground truth to
score against.

## Targets (design — not measured here)

| Metric | Target |
|---|---|
| P50 ingestion (100-page contract) | < 30s |
| P95 query latency | < 2.5s |
| Citation precision @1 | ≥ 0.85 |
| Citation recall @5 | ≥ 0.80 |
| Faithfulness | ≥ 0.97 |
| Cost per Q&A turn | < $0.04 |

These are design targets that the eval harness is set up to measure. CI runs
the eval suite with `FakeProvider` (smoke only, accuracy gates skipped); the
hermetic baseline above is the only number checked in. Live-provider numbers
go in the "Live Eval (BYOK)" section below.

## Bench

`bench/bench.py` measures the chunk → embed → search → answer pipeline at
three preset scales (10 / 100 / 1000 docs) and prints a columnar latency
table. Numbers below come from `bench/results/baseline_small.json`.

```
# lexscribe bench — small (10 docs, 50 queries)
# 20260505T232117Z, fake-provider, in-process
## ingestion
docs/sec   : 326.09
chunks/sec : 2282.62
chunks     : 70
## per-stage latency (ms)
stage       p50      p95      p99      p999     max
parse       0.50     0.70     0.70     0.70     0.70
chunk       0.18     0.21     0.21     0.21     0.21
embed       0.11     0.15     0.15     0.15     0.15
classify    0.02     0.03     0.03     0.03     0.03
## retrieval latency (ms)
stage       p50      p95      p99      p999     max
bm25        0.08     0.13     0.16     0.16     0.16
dense       0.55     0.59     0.62     0.62     0.62
fusion      0.01     0.02     0.04     0.04     0.04
rerank      0.80     0.92     0.97     0.97     0.97
## end-to-end Q&A latency (ms)
stage       p50      p95      p99      p999     max
e2e_qa      1.50     1.70     1.85     1.85     1.85
```

Local-machine numbers on M-series Mac. Reproduce with `make bench`. See
[bench/README.md](bench/README.md) for what is and is not measured —
short version: this exercises the in-process retrieval+provider path with
`FakeProvider`, not pgvector or live LLMs.

For the legacy single-script bench (`bench.sh`):

```bash
N=50 ./bench.sh > runs/bench-$(date +%s).json
```

That harness drives `answer_question` against the three-page demo corpus
and reports a single P50/P95/P99 line. Use `bench/bench.py` for stage
breakdowns and multi-scale runs.

## Architecture (one diagram)

```
            ┌───────────┐    presigned PUT    ┌─────────┐
   client ─►│  /docs    │ ──────────────────► │  MinIO  │
            │  /qa      │                     │   / S3  │
            └─────┬─────┘                     └────┬────┘
                  │ enqueue (parse)                │ object_created
                  ▼                                │
          ┌──────────────┐    ┌──────────────┐    │
          │ celery parse │ ─► │ celery embed │ ◄──┘
          └──────┬───────┘    └──────┬───────┘
                 │                   │
                 ▼                   ▼
            ┌───────────────────────────────┐
            │        Postgres + pgvector    │
            │  documents · chunks(tsv,vec)  │
            │  spans · failed_jobs          │
            └───────────────────────────────┘
                       ▲
                       │  hybrid: BM25 + dense + RRF + rerank
                       │
                  ┌────┴────┐
                  │ /qa     │ ─► LLMProvider.generate (structured)
                  └─────────┘     → Citation list filtered to chunk indices
```

## Tests

| Suite | Marker | Default |
|---|---|---|
| unit | (none) | run |
| contract | `contract` | run (schemathesis) |
| integration | `integration` | skipped unless `RUN_INTEGRATION=1` |

CI runs `lint`, `typecheck`, `test` (Python 3.11 + 3.12 matrix), `contract`,
`eval-smoke`, and on `main` builds both Docker images.

## What this is *not*

* **Not legal advice.** The clause classifier is a small keyword baseline plus
  a span schema; serious deployments would replace it with a labelled-data
  classifier and human review.
* **Not multi-tenant complete.** The `tenants` table and the partial index
  exist; the auth layer that enforces `tenant_id` on every query does not.
  Wire it in via FastAPI dependencies before exposing this to anyone.
* **Not optimised for huge corpora.** Hybrid search is fine into the low
  millions of chunks. Beyond that, swap pgvector HNSW for a dedicated vector
  service or shard by tenant.
* **Not OCR-tuned.** The parse stage falls back to OCR when text density is
  low, but OCR quality and cost vary by document; the threshold should be
  measured per data set.
* **Real EDGAR contracts in the seed are for demonstration only.** Production
  data rooms have access controls, lineage, and entitlements that this
  study does not implement. The seed bypasses the worker DAG and chunks
  in-process; the DB-backed ingest pipeline is exercised separately by the
  integration tests.

## Known issues / deferred

* **Cosign signing of images** — wired in `release.yml` later; current build
  job builds but does not push or sign.
* **Trivy / SBOM** — left out of CI to keep the green build under five
  minutes; `release.yml` is the natural home for them.
* **EDGAR ingestion via the worker DAG** — `seed_edgar.py` chunks and
  embeds in-process so the demo runs without Postgres/Redis/MinIO. The
  worker DAG path (`lexscribe_worker.tasks.run_pipeline_sync`) is exercised
  by the synthetic seed and integration tests; wiring real EDGAR contracts
  through it is a follow-up.

## Live Eval (BYOK)

The hermetic baseline above uses `FakeLLMProvider` and exercises only the
retrieval pipeline. To measure real generation quality (faithfulness,
refusal rate, real latency, real cost) against a live model, use BYOK:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
mkdir -p eval/runs
lexscribe eval run \
  --suite mna_v1 \
  --provider anthropic \
  --model claude-sonnet-4-7 \
  --output eval/runs/$(date -u +%Y%m%dT%H%M%SZ).json
```

Rough cost: ~$1–3 for a full `mna_v1` run on Sonnet 4.7, depending on
retrieval depth and answer length. Numbers are not committed to the repo;
keep them in `eval/runs/` (gitignored) or a private notebook. The wiring
point for adding new providers is `packages/eval/lexscribe_eval/runner.py`.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Sai Asish Y.
