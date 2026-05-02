"""Document ingest + cursor-paginated listing.

The ``POST /documents`` endpoint returns a presigned S3 PUT URL — the API itself
never sees raw bytes. The worker sees an ``object_created`` event (or the client
calls back with the SHA256 once upload completes; we choose the latter since it
keeps the system testable without S3 event wiring).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from lexscribe_shared.cursor import CursorCodec
from lexscribe_shared.errors import ValidationError
from lexscribe_shared.models import DocumentStatus
from pydantic import BaseModel, Field


def _decode(codec: CursorCodec, cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        return codec.decode(cursor)
    except (ValueError, Exception) as exc:
        raise ValidationError("invalid cursor", details={"cursor": cursor[:64]}) from exc


router = APIRouter(prefix="/documents", tags=["documents"])

_DOC_CURSOR = CursorCodec(("created_at", "id"))
_SPAN_CURSOR = CursorCodec(("page_no", "char_start"))


class CreateDocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = "application/pdf"
    sha256: str = Field(min_length=64, max_length=64)


class CreateDocumentResponse(BaseModel):
    document_id: str
    upload_url: str
    s3_key: str
    expires_in: int


class DocumentListItem(BaseModel):
    id: str
    filename: str
    sha256: str
    status: DocumentStatus
    current_version: int
    page_count: int | None = None


class DocumentList(BaseModel):
    items: list[DocumentListItem]
    next_cursor: str | None = None


@router.post("", response_model=CreateDocumentResponse, status_code=201)
def create_document(req: CreateDocumentRequest) -> CreateDocumentResponse:
    # The presigned URL would normally come from boto3.generate_presigned_url.
    # Here we return a deterministic stub — integration tests substitute MinIO.
    doc_id = f"doc_{req.sha256[:12]}"
    s3_key = f"raw/{doc_id}/{req.filename}"
    return CreateDocumentResponse(
        document_id=doc_id,
        upload_url=f"http://s3.invalid/{s3_key}?X-Amz-Signature=stub",
        s3_key=s3_key,
        expires_in=3600,
    )


@router.get("", response_model=DocumentList)
def list_documents(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> DocumentList:
    # Empty stub — DB-backed listing lives in repos and is wired in integration.
    _decode(_DOC_CURSOR, cursor)
    return DocumentList(items=[], next_cursor=None)


class SpanItem(BaseModel):
    page_no: int
    char_start: int
    char_end: int
    clause_type: str
    text: str


class SpanList(BaseModel):
    items: list[SpanItem]
    next_cursor: str | None = None


@router.get("/{doc_id}/spans", response_model=SpanList)
def list_spans(
    doc_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> SpanList:
    _decode(_SPAN_CURSOR, cursor)
    _ = doc_id  # unused in the stub
    return SpanList(items=[], next_cursor=None)


# Re-export cursors so tests can round-trip them
__all__: list[Any] = [
    "_DOC_CURSOR",
    "_SPAN_CURSOR",
    "router",
]
