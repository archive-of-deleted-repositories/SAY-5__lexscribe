from __future__ import annotations

from lexscribe_shared.errors import (
    NotFoundError,
    ProviderError,
    RateLimitedError,
    RetryableError,
    ValidationError,
)


def test_validation_error_envelope() -> None:
    e = ValidationError("bad input", details={"field": "x"})
    env = e.envelope("req-1")
    assert env.code == "validation_error"
    assert env.retryable is False
    assert env.request_id == "req-1"
    assert env.details == {"field": "x"}


def test_retryable_error_marks_retryable() -> None:
    e = RetryableError("transient")
    assert e.envelope().retryable is True


def test_not_found_status() -> None:
    assert NotFoundError("missing").http_status == 404


def test_rate_limited_is_retryable() -> None:
    e = RateLimitedError("slow down")
    assert e.envelope().retryable is True
    assert e.http_status == 429


def test_provider_error_is_retryable_and_502() -> None:
    e = ProviderError("upstream down")
    assert e.http_status == 502
    assert e.envelope().retryable is True
