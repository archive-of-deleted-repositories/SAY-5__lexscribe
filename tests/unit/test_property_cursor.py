"""Property-based round-trip tests for cursor encode/decode."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from lexscribe_shared.cursor import CursorCodec, decode_cursor, encode_cursor

# A timestamp string and an opaque id. We treat both as strings because that is
# the on-the-wire shape — see ``CursorCodec(("created_at", "id"))``.
_TIMESTAMP = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-:T.Z"),
    min_size=1,
    max_size=40,
)
_ID = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=64,
)


@given(ts=_TIMESTAMP, ident=_ID)
def test_round_trip_low_level(ts: str, ident: str) -> None:
    """``decode_cursor(encode_cursor(p))`` returns ``p`` for any (timestamp, id)."""

    payload = {"created_at": ts, "id": ident}
    encoded = encode_cursor(payload)
    assert decode_cursor(encoded) == payload


@given(ts=_TIMESTAMP, ident=_ID)
def test_round_trip_through_codec(ts: str, ident: str) -> None:
    codec = CursorCodec(("created_at", "id"))
    encoded = codec.encode(created_at=ts, id=ident)
    decoded = codec.decode(encoded)
    assert decoded == {"created_at": ts, "id": ident}


@given(ts=_TIMESTAMP, ident=_ID)
def test_encoded_cursor_is_url_safe(ts: str, ident: str) -> None:
    encoded = encode_cursor({"created_at": ts, "id": ident})
    assert "/" not in encoded
    assert "+" not in encoded
    assert "=" not in encoded


@given(
    extras=st.dictionaries(
        keys=st.text(min_size=1, max_size=10).filter(lambda s: s not in {"created_at", "id"}),
        values=st.one_of(st.integers(), st.text(max_size=20), st.booleans()),
        max_size=4,
    ),
    ts=_TIMESTAMP,
    ident=_ID,
)
def test_extra_fields_are_preserved(extras: dict[str, object], ts: str, ident: str) -> None:
    payload: dict[str, object] = {"created_at": ts, "id": ident, **extras}
    assert decode_cursor(encode_cursor(payload)) == payload
