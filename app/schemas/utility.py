from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    filters: Optional[dict[str, Any]] = None


class SearchHit(BaseModel):
    id: int
    type: str
    score: Optional[float] = None
    payload: dict[str, Any]


class SearchResponse(BaseModel):
    total: int
    hits: List[SearchHit]


class ImportRequest(BaseModel):
    source: str
    items: List[dict[str, Any]]
    dry_run: bool = False


class ImportResult(BaseModel):
    index: int
    ok: bool
    error: Optional[str] = None


class ImportResponse(BaseModel):
    total: int
    processed: int
    succeeded: int
    failed: int
    results: List[ImportResult]


class ImportCatalogError(BaseModel):
    row: int
    error: str


class ImportCatalogResponse(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: List[ImportCatalogError]


class StockImportResponse(BaseModel):
    rows_scanned: int
    updated: int
    unchanged: int
    skipped_no_product: int
    skipped_unsupported_brand: int
    skipped_invalid_sku: int
    skipped_invalid_qty: int
    skipped_duplicate: int
    empty_qty_treated_as_zero: int
    errors: int


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class RagAskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class RagQueryHit(BaseModel):
    chunk_id: int
    document_id: int
    document_title: Optional[str] = None
    document_source: Optional[str] = None
    chunk_index: int
    text: str
    score: Optional[float] = None


class RagSource(BaseModel):
    document_id: int
    document_title: str
    document_source: Optional[str] = None
    chunk_indices: List[int]


class RagQueryResponse(BaseModel):
    total: int
    hits: List[RagQueryHit]


class RagIngestTextRequest(BaseModel):
    title: str
    source: Optional[str] = None
    text: str
    chunk_size: int | None = Field(default=1000, ge=1)
    chunk_overlap: int | None = Field(default=200, ge=0)


class RagIngestTextResponse(BaseModel):
    document_id: int
    title: str
    source: Optional[str]
    chunks_count: int
    chunk_size: int
    chunk_overlap: int


class RagAskResponse(BaseModel):
    query: str
    answer: str
    matches: List[RagQueryHit]
    sources: List[RagSource]


__all__ = [
    "SearchRequest",
    "SearchResponse",
    "SearchHit",
    "ImportRequest",
    "ImportResponse",
    "ImportResult",
    "ImportCatalogResponse",
    "ImportCatalogError",
    "StockImportResponse",
    "RagQueryRequest",
    "RagQueryResponse",
    "RagQueryHit",
    "RagSource",
    "RagIngestTextRequest",
    "RagIngestTextResponse",
    "RagAskRequest",
    "RagAskResponse",
]
