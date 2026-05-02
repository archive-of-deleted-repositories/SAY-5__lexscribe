"""Prometheus metrics + ASGI mount."""

from __future__ import annotations

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


async def _scrape(_: Request) -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


def build_metrics_app() -> Starlette:
    return Starlette(routes=[Route("/", _scrape)])
