"""Prometheus metrics + ASGI mount.

Prometheus ``Histogram`` is kept for the end-to-end ``/qa`` latency where
25 ms-grained buckets are fine. Sub-millisecond retrieval stages
(``bm25``, ``dense``, ``fusion``, ``rerank``) are tracked by
:class:`lexscribe_shared.hdr.HdrHistogram` and exported on scrape via
``HdrHistogram.export_prometheus``.
"""

from __future__ import annotations

from lexscribe_retrieval.search import STAGE_HDR as _RETRIEVE_STAGE_HDR
from lexscribe_shared.hdr import HdrHistogram
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

REGISTRY = CollectorRegistry()

ingest_queue_depth = Gauge(
    "lexscribe_ingest_queue_depth",
    "Pending tasks in each ingest queue",
    labelnames=("queue",),
    registry=REGISTRY,
)
dlq_size = Gauge(
    "lexscribe_dlq_size",
    "Rows currently in failed_jobs",
    registry=REGISTRY,
)
qa_latency = Histogram(
    "lexscribe_qa_latency_seconds",
    "End-to-end /qa latency",
    buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0),
    registry=REGISTRY,
)
cost_total = Counter(
    "lexscribe_cost_usd_total",
    "Cumulative LLM spend in USD",
    labelnames=("tenant",),
    registry=REGISTRY,
)

# Sub-millisecond retrieval-stage histograms live in the retrieval package
# (HybridSearcher records into them on every call). The metrics endpoint
# pulls the same module-level dict so scrape output reflects live recording.
RETRIEVE_STAGES = ("bm25", "dense", "fusion", "rerank")
retrieve_stage_hdr: dict[str, HdrHistogram] = _RETRIEVE_STAGE_HDR


def _hdr_exposition() -> str:
    blocks: list[str] = []
    for stage in RETRIEVE_STAGES:
        hdr = retrieve_stage_hdr.get(stage)
        if hdr is None or hdr.total_count() == 0:
            continue
        blocks.append(
            hdr.export_prometheus(
                f"lexscribe_retrieve_{stage}_seconds",
                labels={"stage": stage},
                help_text=f"HDR-backed retrieval-stage latency for {stage}",
            )
        )
    return "".join(blocks)


async def _scrape(_: Request) -> Response:
    body = generate_latest(REGISTRY) + _hdr_exposition().encode()
    return Response(body, media_type=CONTENT_TYPE_LATEST)


def build_metrics_app() -> Starlette:
    return Starlette(routes=[Route("/", _scrape)])
