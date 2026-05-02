"""OpenTelemetry bootstrap.

Idempotent: calling ``setup_otel`` more than once is a no-op. When ``otel_enabled``
is false we skip the exporter entirely and return a NoOpTracer-equivalent so test
runs do not flake on a missing collector.
"""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from lexscribe_shared.settings import Settings, get_settings

_LOG = logging.getLogger(__name__)
_INITIALISED = False


def setup_otel(settings: Settings | None = None) -> trace.Tracer:
    """Configure global tracer. Safe to call multiple times."""

    global _INITIALISED
    settings = settings or get_settings()
    tracer = trace.get_tracer(settings.service_name, settings.service_version)

    if _INITIALISED or not settings.otel_enabled:
        return tracer

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:  # pragma: no cover
        _LOG.warning("OTel OTLP exporter not installed; tracing disabled")
        _INITIALISED = True
        return tracer

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.env,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    _INITIALISED = True
    return trace.get_tracer(settings.service_name, settings.service_version)


def get_tracer(name: str = "lexscribe") -> trace.Tracer:
    return trace.get_tracer(name)


def span_attrs(**kwargs: Any) -> dict[str, Any]:
    """Drop None-valued attrs and truncate long string lists for span recording."""

    out: dict[str, Any] = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, list) and v and isinstance(v[0], str):
            v = v[:32]
        out[k] = v
    return out
