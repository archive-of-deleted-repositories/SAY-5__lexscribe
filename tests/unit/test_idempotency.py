from __future__ import annotations

from lexscribe_worker.idempotency import IdempotencyStore, InMemoryCache


def test_marking_makes_already_done_true() -> None:
    store = IdempotencyStore(InMemoryCache())
    k = store.key("doc1", 1, "embed")
    assert store.already_done(k) is False
    store.mark_done(k)
    assert store.already_done(k) is True


def test_chunk_idx_disambiguates_keys() -> None:
    store = IdempotencyStore(InMemoryCache())
    k0 = store.key("doc1", 1, "embed", chunk_idx=0)
    k1 = store.key("doc1", 1, "embed", chunk_idx=1)
    store.mark_done(k0)
    assert store.already_done(k0)
    assert not store.already_done(k1)
