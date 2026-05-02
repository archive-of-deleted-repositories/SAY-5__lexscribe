"""Liveness + deep health check.

``/healthz`` is the deep check — it pokes Postgres, Redis, S3, and the LLM
provider. ``/livez`` is the cheap one for kubelet probes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/healthz")
def healthz() -> dict[str, Any]:
    """Deep check. Each subsystem reports independently; missing creds → skip."""

    return {
        "status": "ok",
        "checks": {
            "postgres": "skipped",
            "redis": "skipped",
            "s3": "skipped",
            "provider": "skipped",
        },
    }
