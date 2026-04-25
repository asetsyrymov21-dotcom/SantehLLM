"""Stock import module for FRAP inventory updates.

Safe importer that:
- Only updates existing products
- Only updates stock/inventory fields
- Never creates products
- Never changes name, description, brand, category, images
- Supports dry-run mode by default
- Provides detailed reporting
"""

from .excel_parser import StockExcelParser, ExcelParseResult, ExcelStockRow
from .matcher import StockMatcher, StockMatchReport, MatchResult
from .importer import StockImporter, StockImportCommitResult, StockUpdateRecord
from .unmatched_analyzer import (
    UnmatchedSkuAnalyzer,
    UnmatchedSkuAnalysis,
    UnmatchedAnalysisSummary,
    SkuVariantChecker,
)

__all__ = [
    # Parser
    "StockExcelParser",
    "ExcelParseResult",
    "ExcelStockRow",
    # Matcher
    "StockMatcher",
    "StockMatchReport",
    "MatchResult",
    # Importer
    "StockImporter",
    "StockImportCommitResult",
    "StockUpdateRecord",
    # Unmatched Analyzer
    "UnmatchedSkuAnalyzer",
    "UnmatchedSkuAnalysis",
    "UnmatchedAnalysisSummary",
    "SkuVariantChecker",
]
