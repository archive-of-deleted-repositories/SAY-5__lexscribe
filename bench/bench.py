"""Bench harness for Lexscribe.

Drives synthetic ingest + retrieval + Q&A workloads through the in-process
pipeline and reports per-stage latency percentiles, throughput, and cost.

Three scales:

* small  — 10 docs, 50 queries (default; runs in seconds)
* medium — 100 docs, 200 queries
* large  — 1000 docs, 500 queries

Output:

* columnar plain-text table to stdout
* JSON dump to ``bench/results/<UTC-timestamp>.json``

This measures library + DB-free + provider-free latency on a single host
using ``FakeProvider`` and ``FakeEmbeddingProvider``. It is *not* a model
of production cluster behaviour and does not exercise pgvector, real LLM
costs, network round-trips, or worker scheduling. Use it to spot
regressions in the chunk → embed → search pipeline.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Make the workspace importable when this script is run directly.
_ROOT = Path(__file__).resolve().parent.parent
for _sub in (
    "packages/shared",
    "packages/retrieval",
    "packages/eval",
    "packages/clients/python",
    "services/api",
    "services/ingest-worker",
    "scripts",
):
    p = str(_ROOT / _sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from faker import Faker  # noqa: E402
from lexscribe_api.qa_service import _chunk_to_citation  # noqa: E402
from lexscribe_retrieval.chunker import chunk_pages  # noqa: E402
from lexscribe_retrieval.search import HybridSearcher, IndexedChunk  # noqa: E402
from lexscribe_shared.costing import CostRates, turn_cost  # noqa: E402
from lexscribe_shared.providers import (  # noqa: E402
    FakeEmbeddingProvider,
    FakeLLMProvider,
    GenerationRequest,
    attach_citations,
)
from lexscribe_shared.settings import get_settings  # noqa: E402
from seed import CLAUSES, synth_contract  # noqa: E402

SCALES: dict[str, dict[str, int]] = {
    "small": {"n_docs": 10, "n_queries": 50},
    "medium": {"n_docs": 100, "n_queries": 200},
    "large": {"n_docs": 1000, "n_queries": 500},
}

QUERIES: tuple[str, ...] = (
    "What constitutes a Change of Control?",
    "Who owns intellectual property created during the engagement?",
    "What is the governing law of the agreement?",
    "Are there exclusivity restrictions on the contractor?",
    "What are the termination conditions?",
    "Does the contractor indemnify the customer?",
    "How much notice is required to terminate for cause?",
    "Are moral rights assigned along with intellectual property?",
)


@dataclass
class StageTimings:
    parse: list[float] = field(default_factory=list)
    chunk: list[float] = field(default_factory=list)
    embed: list[float] = field(default_factory=list)
    classify: list[float] = field(default_factory=list)
    bm25: list[float] = field(default_factory=list)
    dense: list[float] = field(default_factory=list)
    fusion: list[float] = field(default_factory=list)
    rerank: list[float] = field(default_factory=list)
    end_to_end_qa: list[float] = field(default_factory=list)
    cost_per_turn: list[float] = field(default_factory=list)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def _classify_stub(text: str) -> list[tuple[str, str]]:
    """Match the classifier shape used in the worker DAG. Cheap on purpose."""

    keywords = {
        "change of control": "change_of_control",
        "intellectual property": "ip_assignment",
        "exclusivity": "exclusivity",
        "exclusive": "exclusivity",
        "terminate": "termination",
        "indemnif": "indemnity",
        "governed by": "governing_law",
    }
    lower = text.lower()
    out: list[tuple[str, str]] = []
    for needle, label in keywords.items():
        if needle in lower:
            out.append((label, needle))
    return out


def run_ingest(
    n_docs: int,
    *,
    seed: int,
    timings: StageTimings,
    embed_dim: int = 128,
) -> tuple[HybridSearcher, int]:
    """Synthesise + ingest ``n_docs`` documents, return a searcher + chunk count."""

    Faker.seed(seed)
    random.seed(seed)
    fake = Faker()
    embedder = FakeEmbeddingProvider(dim=embed_dim)
    indexed: list[IndexedChunk] = []

    for i in range(n_docs):
        # parse stage — emit (page_no, text). We bypass the actual PDF parser
        # since the synthetic generator gives us pages directly. Time the
        # construction so the parse line is at least non-zero.
        t0 = time.perf_counter()
        contract = synth_contract(fake, n_pages=6)
        timings.parse.append((time.perf_counter() - t0) * 1000.0)

        # chunk
        t0 = time.perf_counter()
        chunks = chunk_pages(list(contract.pages), target_chars=1200, overlap_chars=150)
        timings.chunk.append((time.perf_counter() - t0) * 1000.0)
        if not chunks:
            continue

        # embed
        t0 = time.perf_counter()
        vecs = embedder.embed([c.text for c in chunks])
        timings.embed.append((time.perf_counter() - t0) * 1000.0)

        # classify (per chunk, then aggregate the per-doc time so the line
        # tracks ingest cost rather than per-chunk cost — keeps scales
        # comparable to parse/chunk/embed which are also per-doc)
        t0 = time.perf_counter()
        for c in chunks:
            _classify_stub(c.text)
        timings.classify.append((time.perf_counter() - t0) * 1000.0)

        for c, vec in zip(chunks, vecs, strict=True):
            indexed.append(
                IndexedChunk(
                    chunk_id=f"doc_synth_{i:05d}::p{c.page_no}::{c.char_start}-{c.char_end}",
                    text=c.text,
                    embedding=tuple(vec),
                )
            )
        # Drop ``CLAUSES`` reference to silence "unused import" without losing
        # the documentation that we *use* its templates via synth_contract.
        _ = CLAUSES

    searcher = HybridSearcher(chunks=indexed, embedder=embedder)
    return searcher, len(indexed)


def run_queries(
    searcher: HybridSearcher,
    n_queries: int,
    *,
    timings: StageTimings,
    seed: int,
) -> None:
    """Drive ``n_queries`` end-to-end Q&A turns through the in-process searcher."""

    rng = random.Random(seed)
    settings = get_settings()
    rates = CostRates(
        in_per_1k=settings.cost_in_per_1k,
        out_per_1k=settings.cost_out_per_1k,
        embed_per_1k=settings.cost_embed_per_1k,
    )
    llm = FakeLLMProvider()

    for _ in range(n_queries):
        q = rng.choice(QUERIES)
        t_e2e = time.perf_counter()

        # Sub-stage timings inside HybridSearcher.search are not directly
        # exposed; we reproduce the BM25/dense/fusion/rerank shape here so
        # the bench has visibility. Total still equals end-to-end.
        from lexscribe_retrieval.fusion import reciprocal_rank_fusion
        from lexscribe_retrieval.search import _cosine

        chunks_list = searcher._chunks  # type: ignore[attr-defined]
        bm25 = searcher._bm25  # type: ignore[attr-defined]
        embedder = searcher._embedder  # type: ignore[attr-defined]
        reranker = searcher._reranker  # type: ignore[attr-defined]
        if not chunks_list or bm25 is None:
            continue

        t = time.perf_counter()
        bm25_scores = bm25.get_scores(q.lower().split())
        bm25_order = sorted(range(len(chunks_list)), key=lambda i: bm25_scores[i], reverse=True)[
            :50
        ]
        timings.bm25.append((time.perf_counter() - t) * 1000.0)

        t = time.perf_counter()
        q_emb = embedder.embed([q])[0]
        dense_scores = [_cosine(q_emb, c.embedding) for c in chunks_list]
        dense_order = sorted(range(len(chunks_list)), key=lambda i: dense_scores[i], reverse=True)[
            :50
        ]
        timings.dense.append((time.perf_counter() - t) * 1000.0)

        t = time.perf_counter()
        fused = reciprocal_rank_fusion([bm25_order, dense_order])
        top_n = [idx for idx, _ in fused[:50]]
        timings.fusion.append((time.perf_counter() - t) * 1000.0)

        t = time.perf_counter()
        candidates_text = [chunks_list[i].text for i in top_n]
        rerank_scores = reranker.rerank(q, candidates_text)
        ranked = sorted(zip(top_n, rerank_scores, strict=False), key=lambda x: x[1], reverse=True)[
            :8
        ]
        timings.rerank.append((time.perf_counter() - t) * 1000.0)

        # Provider call + citation packing — the rest of an end-to-end turn
        chunk_texts = tuple(chunks_list[i].text for i, _ in ranked)
        pool = [
            _chunk_to_citation(chunks_list[i].chunk_id, chunks_list[i].text, float(s))
            for i, s in ranked
        ]
        gen = llm.generate(
            GenerationRequest(
                system="Answer using only the supplied excerpts. Cite by index.",
                user=q,
                chunks=chunk_texts,
                model="fake-1",
            )
        )
        _ = attach_citations(pool, gen.citation_indices)
        cost = turn_cost(tokens_in=gen.tokens_in, tokens_out=gen.tokens_out, rates=rates)
        timings.cost_per_turn.append(cost)

        timings.end_to_end_qa.append((time.perf_counter() - t_e2e) * 1000.0)


def _summarise_stage(name: str, values: list[float]) -> dict[str, float]:
    return {
        "stage": name,
        "n": len(values),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "p99": _percentile(values, 99),
        "p999": _percentile(values, 99.9),
        "max": max(values) if values else 0.0,
    }


def _format_table(rows: list[dict[str, float]]) -> str:
    headers = ("stage", "p50", "p95", "p99", "p999", "max")
    widths = (10, 7, 7, 7, 7, 7)
    out_lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=False))]
    for r in rows:
        out_lines.append(
            "  ".join(
                [
                    str(r["stage"]).ljust(widths[0]),
                    f"{r['p50']:.2f}".ljust(widths[1]),
                    f"{r['p95']:.2f}".ljust(widths[2]),
                    f"{r['p99']:.2f}".ljust(widths[3]),
                    f"{r['p999']:.2f}".ljust(widths[4]),
                    f"{r['max']:.2f}".ljust(widths[5]),
                ]
            )
        )
    return "\n".join(out_lines)


def _print_report(
    *,
    scale: str,
    n_docs: int,
    n_chunks: int,
    n_queries: int,
    ingest_seconds: float,
    timings: StageTimings,
    cost_p95: float,
    cost_mean: float,
    timestamp: str,
) -> str:
    docs_per_sec = n_docs / ingest_seconds if ingest_seconds > 0 else 0.0
    chunks_per_sec = n_chunks / ingest_seconds if ingest_seconds > 0 else 0.0

    ingest_rows = [
        _summarise_stage(s, getattr(timings, s)) for s in ("parse", "chunk", "embed", "classify")
    ]
    retr_rows = [
        _summarise_stage(s, getattr(timings, s)) for s in ("bm25", "dense", "fusion", "rerank")
    ]
    e2e = _summarise_stage("e2e_qa", timings.end_to_end_qa)

    lines = [
        f"# lexscribe bench — {scale} ({n_docs} docs, {n_queries} queries)",
        f"# {timestamp}, fake-provider, in-process",
        "## ingestion",
        f"docs/sec   : {docs_per_sec:.2f}",
        f"chunks/sec : {chunks_per_sec:.2f}",
        f"chunks     : {n_chunks}",
        "## per-stage latency (ms)",
        _format_table(ingest_rows),
        "## retrieval latency (ms)",
        _format_table(retr_rows),
        "## end-to-end Q&A latency (ms)",
        _format_table([e2e]),
        "## cost per turn (USD, FakeProvider — for accounting shape, not real cost)",
        f"mean : {cost_mean:.6f}",
        f"p95  : {cost_p95:.6f}",
        "# Local-machine numbers on M-series Mac. See bench/README.md for methodology.",
    ]
    return "\n".join(lines)


def run_bench(scale: str, *, seed: int = 1234) -> dict[str, object]:
    cfg = SCALES[scale]
    n_docs = cfg["n_docs"]
    n_queries = cfg["n_queries"]
    timings = StageTimings()

    ingest_t0 = time.perf_counter()
    searcher, n_chunks = run_ingest(n_docs, seed=seed, timings=timings)
    ingest_seconds = time.perf_counter() - ingest_t0

    run_queries(searcher, n_queries, timings=timings, seed=seed)

    cost_mean = statistics.fmean(timings.cost_per_turn) if timings.cost_per_turn else 0.0
    cost_p95 = _percentile(timings.cost_per_turn, 95)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    text = _print_report(
        scale=scale,
        n_docs=n_docs,
        n_chunks=n_chunks,
        n_queries=n_queries,
        ingest_seconds=ingest_seconds,
        timings=timings,
        cost_p95=cost_p95,
        cost_mean=cost_mean,
        timestamp=timestamp,
    )

    payload: dict[str, object] = {
        "schema_version": 1,
        "scale": scale,
        "timestamp_utc": timestamp,
        "n_docs": n_docs,
        "n_chunks": n_chunks,
        "n_queries": n_queries,
        "ingest_seconds": ingest_seconds,
        "docs_per_sec": n_docs / ingest_seconds if ingest_seconds > 0 else 0.0,
        "chunks_per_sec": n_chunks / ingest_seconds if ingest_seconds > 0 else 0.0,
        "ingest_stage_ms": {
            s: _summarise_stage(s, getattr(timings, s))
            for s in ("parse", "chunk", "embed", "classify")
        },
        "retrieval_stage_ms": {
            s: _summarise_stage(s, getattr(timings, s))
            for s in ("bm25", "dense", "fusion", "rerank")
        },
        "end_to_end_qa_ms": _summarise_stage("e2e_qa", timings.end_to_end_qa),
        "cost_per_turn_usd": {
            "mean": cost_mean,
            "p95": cost_p95,
        },
        "report": text,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lexscribe bench harness.")
    parser.add_argument(
        "--scale", choices=tuple(SCALES.keys()), default="small", help="workload size"
    )
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="directory to write the JSON artifact (default: bench/results/)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print the report but do not persist a JSON artifact",
    )
    args = parser.parse_args(argv)

    payload = run_bench(args.scale, seed=args.seed)
    print(payload["report"])

    if not args.no_write:
        args.results_dir.mkdir(parents=True, exist_ok=True)
        out = args.results_dir / f"{payload['timestamp_utc']}_{args.scale}.json"
        out.write_text(json.dumps(payload, indent=2))
        print(f"\n# wrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
