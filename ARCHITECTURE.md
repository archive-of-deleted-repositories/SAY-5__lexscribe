# Architecture

## Central data structures

The whole system pivots on three records that flow through the Celery DAG and
end up persisted in Postgres:

```
Page          (doc_version_id, page_no, text, ocr_used)
Chunk         (page_id, char_start, char_end, text, embedding[1536], tsv)
Span          (page_id, char_start, char_end, clause_type, confidence)
```

A `Citation` returned by `/qa` is just a denormalised pointer back to a `Chunk`,
carrying `(doc_id, version, page, char_start, char_end, score)`. Fixing this
shape early was the single most useful design choice — it means a citation is
*addressable* (every byte of context an answer references can be re-fetched
from the source PDF) and eval rubrics can talk about character ranges without
needing to plumb chunk IDs through the API.

`ClauseType` is a closed enum (seven values). Keeping it closed means the span
classifier cannot drift into making up new categories under load, which is the
usual failure mode when the labels are free strings.

## Retrieval

Two retrievers (BM25 over a Postgres `tsvector` GIN index; dense via pgvector
HNSW) produce ranked candidate sets. They are merged with **Reciprocal Rank
Fusion** at `k = 60`. The top 50 fused candidates are reranked by a
cross-encoder, and the top 8 reach the LLM.

Why RRF and not learned fusion? RRF needs no training data, no calibration, and
behaves well when one of the two retrievers is degraded. Score-based fusion
needs the two scores on a shared scale; once you start min-max normalising you
have a tunable knob you have to maintain forever.

The cross-encoder is interface-only (`Reranker` Protocol). The default
implementation in tests is `HeuristicReranker` — token coverage with a length
penalty — because shipping a 100MB BERT-class model into CI doubles install
time for no useful signal. In production, swap to a real cross-encoder by
implementing the same Protocol.

## Generation

`LLMProvider.generate` returns structured output: an `answer` and
`citation_indices: tuple[int, ...]` referencing the input chunk list. The API
filters the candidate `Citation` list down to the indices the model chose. This
is the bit that makes citations un-fakeable: the model is structurally unable
to cite anything that was not retrieved.

## Worker DAG

```
parse_pdf  (queue=parse, concurrency=4)
   └─► chunk
         └─► embed         (queue=embed, concurrency=8, semaphore-gated)
               └─► classify_spans  (queue=classify, concurrency=2)
```

Three queues, three concurrency caps, one Redis semaphore around `embed`. The
caps and semaphore exist for the same reason: each stage stresses a different
upstream (CPU on parse, embedding API on embed, LLM on classify), and mixing
them in one queue causes the slowest stage to starve the others.

Idempotency is keyed on `(doc_id, version, stage [, chunk_idx])` — see
`lexscribe_worker.idempotency.IdempotencyStore`. A re-running task reads the
key first and short-circuits, which protects against duplicate work after a
worker crash mid-ack and removes the need for a Celery dedup plugin.

## Failure handling

Per-chunk transactional ingest. An OCR failure on page 47 of a 200-page PDF
commits pages 1-46 and lands page 47 in `failed_jobs` with the original payload
plus the last error. The retry schedule is `1s, 4s, 16s, 64s` with ±20% jitter,
shared between Celery and in-process callers via
`lexscribe_shared.retry.backoff_delays`. After the retry budget is exhausted
the job moves to the DLQ; replay is a single CLI command
(`lexscribe-worker replay-dlq --limit 10 --no-dry-run`).

## Pagination

All list endpoints are cursor-paginated on `(created_at, id)` (or
`(page_no, char_start)` for spans). Cursors are opaque base64-encoded JSON;
they are validated against a fixed schema before being used in a query. There
is no `count(*)` and no offset — both are O(N) and degrade silently as the
table grows.

## Observability

* **Tracing:** OTel via OTLP. Manual spans around `retrieve, rerank, generate,
  parse_pdf, embed_batch` carry `model, tokens_in, tokens_out, cost_usd,
  chunk_count, cache_hit, retrieved_chunk_ids` (truncated to 32 entries).
* **Metrics:** Prometheus. `lexscribe_qa_latency_seconds` histogram with
  buckets `(0.25, 0.5, 1, 2, 4, 8)` chosen to bracket the 2.5s P95 target.
  `lexscribe_cost_usd_total` counter labelled by tenant.
* **Logs:** structlog JSON with `trace_id`, `span_id`, `request_id`,
  `tenant_id`. The trace correlation hook reads from the active OTel span.

## Schema migrations

Alembic with explicit `up` AND `down` for every revision. The smoke test in
`tests/integration/test_db_round_trip.py` runs `upgrade head` then
`downgrade base` — so a migration that breaks rollback fails CI before it
breaks production.

The `chunks.embedding` HNSW and `chunks.tsv` GIN indexes are created inline in
the initial migration so the round-trip test is one transaction. In production,
swap them for `CREATE INDEX CONCURRENTLY` in an autocommit block — that is a
one-line change and is documented at the call site.

## Provider seam

Every external call (LLM, embeddings) goes through a `Protocol`. Tests use
`FakeProvider`, which is fully deterministic (hash-seeded vectors, first-chunk
echo). That means:

1. CI never reaches Anthropic/OpenAI.
2. The same code path runs in tests, in `bench.sh`, and in production.
3. Switching providers is a constructor argument, not a refactor.

## Tradeoffs we did *not* take

* **No vector search service** (Pinecone/Qdrant/Weaviate). pgvector is good
  enough up to a few million chunks and removes a whole operational surface.
  Beyond that scale, the `HybridSearcher` interface is small enough that
  swapping the dense backend is a 50-line change.
* **No streaming responses.** `/qa` returns the full envelope at once. Streaming
  would force the API to serialise citations *after* the answer, which weakens
  the structural-citation guarantee. Worth revisiting if/when we adopt SSE.
* **No vendor-specific RAG framework.** No LangChain, no LlamaIndex. The full
  hybrid pipeline is ~250 lines of Python and is faster to read than any
  framework's getting-started guide.

## What's deliberately not here

* Multi-tenant auth enforcement at the dependency layer.
* A learned span classifier (the bundled one is a keyword baseline).
* Live-EDGAR ingestion (the synthetic generator covers test needs).
* Cosign / SBOM / Trivy in CI (deferred to release pipeline).
* TypeScript client (Python only by choice).
