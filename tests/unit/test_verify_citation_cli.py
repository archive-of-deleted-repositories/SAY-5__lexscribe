"""Tests for the ``lexscribe verify-citation`` CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from lexscribe_eval.cli import cli
from lexscribe_shared.canonicalize import chunk_hash, doc_canonical_hash


def _write(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload))


@pytest.fixture
def store_payload() -> list[dict]:
    text = "Section 1. The agreement is effective on the closing date."
    full = "Preamble.\n" + text + "\nArticle II. Misc."
    return [
        {
            "doc_id": "doc_x",
            "version": 1,
            "page": 3,
            "char_start": 100,
            "char_end": 100 + len(text),
            "text": text,
            "doc_text": full,
        }
    ]


def test_cli_verify_passes_for_unchanged_chunk(tmp_path: Path, store_payload: list[dict]) -> None:
    rec = store_payload[0]
    citation = {
        "doc_id": rec["doc_id"],
        "version": rec["version"],
        "page": rec["page"],
        "char_start": rec["char_start"],
        "char_end": rec["char_end"],
        "score": 0.9,
        "chunk_hash": chunk_hash(rec["text"]),
        "doc_canonical_hash": doc_canonical_hash(rec["doc_text"]),
    }
    cit_path = tmp_path / "citation.json"
    store_path = tmp_path / "store.json"
    _write(cit_path, citation)
    _write(store_path, store_payload)

    runner = CliRunner()
    result = runner.invoke(cli, ["verify-citation", str(cit_path), "--store", str(store_path)])
    assert result.exit_code == 0, result.output
    assert "OK doc_id=doc_x" in result.output


def test_cli_verify_fails_for_tampered_chunk(tmp_path: Path, store_payload: list[dict]) -> None:
    rec = store_payload[0]
    # citation hash refers to the *original* text; the store will have a
    # tampered version
    citation = {
        "doc_id": rec["doc_id"],
        "version": rec["version"],
        "page": rec["page"],
        "char_start": rec["char_start"],
        "char_end": rec["char_end"],
        "score": 0.9,
        "chunk_hash": chunk_hash(rec["text"]),
    }
    tampered_store = list(store_payload)
    tampered_store[0] = {**rec, "text": rec["text"].replace("effective", "void")}

    cit_path = tmp_path / "citation.json"
    store_path = tmp_path / "store.json"
    _write(cit_path, citation)
    _write(store_path, tampered_store)

    runner = CliRunner()
    result = runner.invoke(cli, ["verify-citation", str(cit_path), "--store", str(store_path)])
    assert result.exit_code == 1
    assert "citation hash mismatch" in result.output


def test_cli_verify_rejects_malformed_citation_json(tmp_path: Path) -> None:
    cit_path = tmp_path / "bad.json"
    cit_path.write_text("{not json}")
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-citation", str(cit_path), "--store", str(cit_path)])
    assert result.exit_code == 2


def test_cli_verify_requires_store(tmp_path: Path, store_payload: list[dict]) -> None:
    rec = store_payload[0]
    citation = {
        "doc_id": rec["doc_id"],
        "version": rec["version"],
        "page": rec["page"],
        "char_start": rec["char_start"],
        "char_end": rec["char_end"],
        "score": 0.9,
        "chunk_hash": chunk_hash(rec["text"]),
    }
    cit_path = tmp_path / "citation.json"
    _write(cit_path, citation)
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-citation", str(cit_path)])
    assert result.exit_code == 2
    assert "--store is required" in result.output
