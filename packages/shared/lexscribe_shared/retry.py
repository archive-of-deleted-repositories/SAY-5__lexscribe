"""Backoff helpers shared by workers and provider clients.

Why a hand-rolled helper instead of just ``tenacity``? Because Celery's own retry
machinery cannot wrap a generator the same way, and we want the *exact* same
schedule for in-process calls and Celery tasks: ``1s, 4s, 16s, 64s`` with ±20%
jitter.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from enum import Enum

from lexscribe_shared.errors import (
    LexscribeError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
    RetryableError,
    ValidationError,
)

DEFAULT_DELAYS = (1.0, 4.0, 16.0, 64.0)


def backoff_delays(
    *, max_attempts: int = 5, jitter: float = 0.2, base: tuple[float, ...] = DEFAULT_DELAYS
) -> Iterator[float]:
    """Yield ``max_attempts - 1`` delays. First attempt has no preceding sleep."""

    for i in range(max_attempts - 1):
        delay = base[i] if i < len(base) else base[-1]
        if jitter:
            delta = delay * jitter
            delay = max(0.0, delay + random.uniform(-delta, delta))
        yield delay


class FailureClass(str, Enum):
    """Coarse-grained verdict used by callers to decide retry vs DLQ."""

    retryable = "retryable"
    permanent = "permanent"


def _classify_failure(exc: BaseException) -> FailureClass:
    """Map a raised exception to a retry/DLQ verdict.

    Decision table:

    * ``RetryableError`` (and subclasses such as ``RateLimitedError``) → retry
    * ``ProviderError`` (upstream failure, retryable=True)              → retry
    * ``ValidationError`` / ``NotFoundError``                           → permanent
    * Other ``LexscribeError`` whose ``retryable`` attribute is True    → retry
    * Built-in ``TimeoutError`` / ``ConnectionError``                   → retry
    * Anything else                                                     → permanent
    """

    if isinstance(exc, RetryableError):
        return FailureClass.retryable
    if isinstance(exc, RateLimitedError):
        return FailureClass.retryable
    if isinstance(exc, ProviderError):
        return FailureClass.retryable
    if isinstance(exc, ValidationError | NotFoundError):
        return FailureClass.permanent
    if isinstance(exc, LexscribeError):
        return FailureClass.retryable if exc.retryable else FailureClass.permanent
    if isinstance(exc, TimeoutError | ConnectionError):
        return FailureClass.retryable
    return FailureClass.permanent
