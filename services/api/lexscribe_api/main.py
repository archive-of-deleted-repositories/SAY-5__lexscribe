"""FastAPI app factory + entry point."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lexscribe_shared.errors import LexscribeError
from lexscribe_shared.logging import configure_logging
from lexscribe_shared.otel import setup_otel
from lexscribe_shared.settings import get_settings

from lexscribe_api.metrics import build_metrics_app
from lexscribe_api.routers import documents, health, qa


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    setup_otel(settings)

    app = FastAPI(
        title="Lexscribe API",
        version=settings.service_version,
        description="M&A diligence copilot — span-cited answers over uploaded contracts.",
    )

    @app.middleware("http")
    async def request_id_mw(
        request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]
    ) -> JSONResponse:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(LexscribeError)
    async def domain_exc_handler(request: Request, exc: LexscribeError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.envelope(rid).model_dump(),
        )

    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(qa.router)
    app.mount("/metrics", build_metrics_app())

    return app


app = create_app()
