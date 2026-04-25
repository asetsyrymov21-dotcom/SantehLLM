"""PDF Enrichment Service for flagged products."""

from .service import PdfEnrichmentService
from .models import (
    EnrichmentResult,
    EnrichmentSummary,
    ProductEnrichmentRecord,
    PdfPageDump,
    PdfTextDump,
    SkuIndex,
)
from .repository import SavedPdfRepository
from .bootstrap import build_pdf_dump_and_index

__all__ = [
    "PdfEnrichmentService",
    "EnrichmentResult",
    "EnrichmentSummary",
    "ProductEnrichmentRecord",
    "PdfPageDump",
    "PdfTextDump",
    "SkuIndex",
    "SavedPdfRepository",
    "build_pdf_dump_and_index",
]
