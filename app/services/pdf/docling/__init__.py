"""
Docling-based PDF extraction for complex catalog pages.

Proof of concept for handling:
- Table pages (structured data)
- Gallery pages (images with SKUs)

Usage:
    from app.services.pdf.docling import DoclingExtractor
    
    extractor = DoclingExtractor()
    result = extractor.extract_page("catalog.pdf", page_number=20)
    
    if result.page_type == "table":
        print(result.table_data)
    elif result.page_type == "gallery":
        print(result.image_items)
"""

from .models import ExtractionResult, PageType, TableRow, ImageItem
from .classifier import PageClassifier
from .extractor import DoclingExtractor

__all__ = [
    "ExtractionResult",
    "PageType", 
    "TableRow",
    "ImageItem",
    "PageClassifier",
    "DoclingExtractor",
]