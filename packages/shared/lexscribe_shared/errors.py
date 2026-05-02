"""Error envelope shared by API, workers, and clients."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    """Wire-format error returned by every endpoint."""

    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None
    details: dict[str, Any] | None = Field(default=None)


class LexscribeError(Exception):
    """Base exception. Subclasses set ``code`` and ``retryable``."""

    code: str = "internal_error"
    retryable: bool = False
    http_status: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def envelope(self, request_id: str | None = None) -> ErrorEnvelope:
        return ErrorEnvelope(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            request_id=request_id,
            details=self.details,
        )


class ValidationError(LexscribeError):
    code = "validation_error"
    http_status = 422


class NotFoundError(LexscribeError):
    code = "not_found"
    http_status = 404


class RetryableError(LexscribeError):
    """Transient failure: the caller (or Celery) should retry with backoff."""

    code = "retryable_error"
    retryable = True
    http_status = 503


class ProviderError(LexscribeError):
    """Upstream LLM/embedding provider failed."""

    code = "provider_error"
    retryable = True
    http_status = 502


class RateLimitedError(RetryableError):
    code = "rate_limited"
    http_status = 429
