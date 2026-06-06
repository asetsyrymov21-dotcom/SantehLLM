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
    filename: str = ""
    selected_sheet: Optional[str] = None
    sheets_checked: int = 0
    sheet_stats: List[dict[str, Any]] = Field(default_factory=list)
    rows_scanned: int
    sku_found: int = 0
    updated: int
    unchanged: int
    skipped_no_product: int
    skipped_unsupported_brand: int
    unsupported_brand_breakdown: dict[str, int] = Field(default_factory=dict)
    skipped_invalid_sku: int
    skipped_invalid_qty: int
    skipped_duplicate: int
    empty_qty_treated_as_zero: int
    first_unmatched_skus: List[str] = Field(default_factory=list)
    first_duplicate_skus: List[str] = Field(default_factory=list)
    errors: int


class CatalogExcelImportResponse(BaseModel):
    filename: str
    sheet: str
    header_row: int
    raw_rows: int
    mapped_rows: int
    built_products: int
    inserted: int
    updated: int
    failed: int
    needs_pdf_enrichment: int
    name_fallback_to_sku: int
    title_empty_in_excel: int
    weak_title_after_normalize: int
    title_lost_in_mapper: int
    title_column_not_mapped: int


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


class AssistantMemoryLookupRequest(BaseModel):
    question: str = Field(..., min_length=1)
    intent: str | None = None
    status: str = "approved"


class AssistantMemoryEntry(BaseModel):
    id: int
    normalized_question: str
    raw_question_example: str
    intent: str
    answer_text: str
    source_product_ids: List[int] = Field(default_factory=list)
    source_document_ids: List[int] = Field(default_factory=list)
    status: str
    hit_count: int

    model_config = {"from_attributes": True}


class AssistantMemoryLookupResponse(BaseModel):
    found: bool
    entry: AssistantMemoryEntry | None = None


class AssistantMemoryStoreRequest(BaseModel):
    question: str = Field(..., min_length=1)
    intent: str
    answer_text: str = Field(..., min_length=1)
    source_product_ids: List[int] = Field(default_factory=list)
    source_document_ids: List[int] = Field(default_factory=list)
    status: str = "draft"
    meta_json: dict[str, Any] | None = None


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
    "CatalogExcelImportResponse",
    "RagQueryRequest",
    "RagQueryResponse",
    "RagQueryHit",
    "RagSource",
    "RagIngestTextRequest",
    "RagIngestTextResponse",
    "RagAskRequest",
    "RagAskResponse",
    "AssistantMemoryLookupRequest",
    "AssistantMemoryLookupResponse",
    "AssistantMemoryStoreRequest",
    "AssistantMemoryEntry",
]
