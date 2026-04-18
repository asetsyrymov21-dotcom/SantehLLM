"""
PDF Bootstrap Module - one-time PDF processing for enrichment.

Builds:
- PdfTextDump: page-level raw text dumps
- SkuIndex: SKU -> candidate pages mapping

Usage:
    from app.services.pdf_enrichment.bootstrap import build_pdf_dump_and_index
    
    build_pdf_dump_and_index(
        pdf_path="catalog.pdf",
        dump_path="catalog_pages.json",
        index_path="catalog_sku_index.json",
        start_page=1,
        end_page=None
    )
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pdfplumber

from app.services.pdf.normalizer import normalize_sku, normalize_text
from .models import PdfPageDump, PdfTextDump, SkuIndex

logger = logging.getLogger(__name__)


# SKU regex pattern - matches patterns like G10101, G10101-13, G10101-13B
SKU_PATTERN = re.compile(
    r"\b([A-Z]\d{3,}(?:-\d{1,3}[A-Z0-9]?)?)\b",
    re.IGNORECASE
)


def extract_skus_from_text(text: str) -> list[str]:
    """Extract all SKU-like patterns from text.
    
    Args:
        text: Raw text to search
        
    Returns:
        List of normalized SKUs found
    """
    if not text:
        return []
    
    skus = set()
    for match in SKU_PATTERN.finditer(text):
        sku = normalize_sku(match.group(1))
        if sku and len(sku) >= 4:  # Filter false positives
            skus.add(sku)
    
    return sorted(list(skus))


def build_pdf_dump_and_index(
    pdf_path: Path | str,
    dump_path: Path | str,
    index_path: Path | str,
    start_page: int = 1,
    end_page: Optional[int] = None,
) -> tuple[PdfTextDump, SkuIndex]:
    """Build PDF text dump and SKU index from a PDF file.
    
    This is the bootstrap function that:
    1. Reads PDF page by page
    2. Extracts raw text from each page
    3. Finds all SKUs using regex
    4. Saves dump (full page texts) and index (sku -> pages mapping)
    
    Args:
        pdf_path: Path to the PDF file
        dump_path: Where to save the JSON dump
        index_path: Where to save the JSON index
        start_page: First page to process (1-indexed)
        end_page: Last page to process (None = all pages)
        
    Returns:
        Tuple of (PdfTextDump, SkuIndex)
        
    Raises:
        FileNotFoundError: If PDF doesn't exist
        Exception: If PDF reading fails
    """
    pdf_path = Path(pdf_path)
    dump_path = Path(dump_path)
    index_path = Path(index_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    logger.info("=" * 60)
    logger.info("BOOTSTRAP: Building PDF dump and index")
    logger.info(f"  PDF: {pdf_path}")
    logger.info(f"  Dump: {dump_path}")
    logger.info(f"  Index: {index_path}")
    logger.info(f"  Pages: {start_page} to {end_page or 'end'}")
    logger.info("=" * 60)
    
    pages: list[PdfPageDump] = []
    sku_to_pages: dict[str, list[int]] = {}
    
    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        actual_end = min(end_page, total_pages) if end_page else total_pages
        
        logger.info(f"PDF has {total_pages} pages, processing {start_page}-{actual_end}")
        
        for page_num in range(start_page, actual_end + 1):
            try:
                page = pdf.pages[page_num - 1]
                raw_text = page.extract_text() or ""
                
                # Normalize text for consistent processing
                normalized_text = normalize_text(raw_text)
                
                # Extract SKUs from this page
                skus_found = extract_skus_from_text(normalized_text)
                
                # Create page dump
                page_dump = PdfPageDump(
                    page_number=page_num,
                    raw_text=normalized_text,
                    skus_found=skus_found,
                )
                pages.append(page_dump)
                
                # Update SKU index
                for sku in skus_found:
                    if sku not in sku_to_pages:
                        sku_to_pages[sku] = []
                    if page_num not in sku_to_pages[sku]:
                        sku_to_pages[sku].append(page_num)
                
                # Progress logging
                if (page_num - start_page + 1) % 10 == 0 or page_num == start_page:
                    logger.info(
                        f"  Processed page {page_num}/{actual_end} - "
                        f"found {len(skus_found)} SKUs"
                    )
                    
            except Exception as e:
                logger.warning(f"  Error processing page {page_num}: {e}")
                # Still add page with empty text to maintain page numbering
                pages.append(PdfPageDump(
                    page_number=page_num,
                    raw_text="",
                    skus_found=[],
                ))
    
    # Create dump object
    created_at = datetime.utcnow().isoformat()
    pdf_dump = PdfTextDump(
        pdf_path=str(pdf_path),
        created_at=created_at,
        page_count=len(pages),
        pages=pages,
    )
    
    # Create index object
    sku_index = SkuIndex(
        pdf_path=str(pdf_path),
        created_at=created_at,
        sku_to_pages=sku_to_pages,
    )
    
    # Save to JSON
    _save_json(dump_path, pdf_dump.to_dict())
    _save_json(index_path, sku_index.to_dict())
    
    logger.info("=" * 60)
    logger.info("BOOTSTRAP COMPLETE:")
    logger.info(f"  Pages processed: {len(pages)}")
    logger.info(f"  Unique SKUs indexed: {len(sku_to_pages)}")
    logger.info(f"  Dump saved: {dump_path}")
    logger.info(f"  Index saved: {index_path}")
    logger.info("=" * 60)
    
    return pdf_dump, sku_index


def _save_json(path: Path, data: dict) -> None:
    """Save data to JSON file with proper encoding.
    
    Args:
        path: Path to save to
        data: Dictionary to serialize
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_pdf_dump(dump_path: Path | str) -> PdfTextDump:
    """Load PDF text dump from JSON file.
    
    Args:
        dump_path: Path to the JSON dump file
        
    Returns:
        PdfTextDump object
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    dump_path = Path(dump_path)
    if not dump_path.exists():
        raise FileNotFoundError(f"Dump file not found: {dump_path}")
    
    with open(dump_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return PdfTextDump.from_dict(data)


def load_sku_index(index_path: Path | str) -> SkuIndex:
    """Load SKU index from JSON file.
    
    Args:
        index_path: Path to the JSON index file
        
    Returns:
        SkuIndex object
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    index_path = Path(index_path)
    if not index_path.exists():
        raise FileNotFoundError(f"Index file not found: {index_path}")
    
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return SkuIndex.from_dict(data)