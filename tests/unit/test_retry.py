from __future__ import annotations

from lexscribe_shared.retry import DEFAULT_DELAYS, backoff_delays


def test_no_jitter_emits_canonical_schedule() -> None:
    delays = list(backoff_delays(max_attempts=5, jitter=0.0))
    assert delays == list(DEFAULT_DELAYS)


def test_max_attempts_one_yields_no_delays() -> None:
    assert list(backoff_delays(max_attempts=1, jitter=0.0)) == []


def test_jitter_stays_within_bounds() -> None:
    for _ in range(20):
        delays = list(backoff_delays(max_attempts=5, jitter=0.2))
        for actual, base in zip(delays, DEFAULT_DELAYS, strict=False):
            lo = base * 0.8
            hi = base * 1.2
            assert lo - 1e-9 <= actual <= hi + 1e-9
