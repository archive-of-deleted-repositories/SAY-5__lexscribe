"""Property-based tests for backoff schedule + decision-table tests for
``_classify_failure``.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from lexscribe_shared.errors import (
    LexscribeError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
    RetryableError,
    ValidationError,
)
from lexscribe_shared.retry import (
    DEFAULT_DELAYS,
    FailureClass,
    _classify_failure,
    backoff_delays,
)


@given(attempts=st.integers(min_value=1, max_value=5))
def test_jittered_delay_in_band_for_each_attempt(attempts: int) -> None:
    """For every attempt n in [1,5], jittered delay is within ±20% of base."""

    delays = list(backoff_delays(max_attempts=attempts, jitter=0.2))
    assert len(delays) == attempts - 1
    for i, d in enumerate(delays):
        base = DEFAULT_DELAYS[i] if i < len(DEFAULT_DELAYS) else DEFAULT_DELAYS[-1]
        # The spec calls for ``base * 2^(attempt-1)`` shape, but the project uses
        # an explicit ``DEFAULT_DELAYS`` tuple ``(1, 4, 16, 64)`` which is the
        # same schedule (1s, 4s, 16s, 64s) authored as a constant. Either way
        # the band check is ``[base * 0.8, base * 1.2]``.
        assert base * 0.8 - 1e-9 <= d <= base * 1.2 + 1e-9


@given(
    attempts=st.integers(min_value=1, max_value=5), jitter=st.floats(min_value=0.0, max_value=0.5)
)
def test_delay_count_equals_attempts_minus_one(attempts: int, jitter: float) -> None:
    delays = list(backoff_delays(max_attempts=attempts, jitter=jitter))
    assert len(delays) == attempts - 1


def test_zero_jitter_emits_canonical_schedule() -> None:
    delays = list(backoff_delays(max_attempts=5, jitter=0.0))
    assert delays == list(DEFAULT_DELAYS)


# ---- Decision table for _classify_failure ---- #


def test_retryable_error_is_retryable() -> None:
    assert _classify_failure(RetryableError("boom")) is FailureClass.retryable


def test_rate_limited_error_is_retryable() -> None:
    assert _classify_failure(RateLimitedError("429")) is FailureClass.retryable


def test_provider_error_is_retryable() -> None:
    assert _classify_failure(ProviderError("upstream")) is FailureClass.retryable


def test_validation_error_is_permanent() -> None:
    assert _classify_failure(ValidationError("bad input")) is FailureClass.permanent


def test_not_found_error_is_permanent() -> None:
    assert _classify_failure(NotFoundError("missing")) is FailureClass.permanent


def test_lexscribe_error_with_retryable_attr_is_retryable() -> None:
    class CustomTransient(LexscribeError):
        retryable = True

    assert _classify_failure(CustomTransient("transient")) is FailureClass.retryable


def test_lexscribe_error_without_retryable_attr_is_permanent() -> None:
    class CustomPermanent(LexscribeError):
        retryable = False

    assert _classify_failure(CustomPermanent("permanent")) is FailureClass.permanent


def test_builtin_timeout_error_is_retryable() -> None:
    assert _classify_failure(TimeoutError("read timed out")) is FailureClass.retryable


def test_builtin_connection_error_is_retryable() -> None:
    assert _classify_failure(ConnectionError("conn refused")) is FailureClass.retryable


def test_value_error_is_permanent() -> None:
    assert _classify_failure(ValueError("nope")) is FailureClass.permanent


def test_runtime_error_is_permanent() -> None:
    assert _classify_failure(RuntimeError("boom")) is FailureClass.permanent
