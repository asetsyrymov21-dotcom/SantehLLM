"""
PDF inspector module for getting metadata and checking extractability.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

if TYPE_CHECKING:
    pass  # for type checking only

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfInfo:
    """Information about a PDF file."""
    
    page_count: int
    file_size_mb: float
    is_text_extractable: bool
    file_path: str
    
    def __repr__(self) -> str:
        return (
            f"PdfInfo(path={self.file_path!r}, "
            f"pages={self.page_count}, "
            f"size={self.file_size_mb:.2f}MB, "
            f"text_extractable={self.is_text_extractable})"
        )


def inspect_pdf(pdf_path: str | Path) -> PdfInfo:
    """
    Inspect PDF file and return metadata.
    
    Opens PDF without loading all pages into memory.
    Performs quick check for text extractability on first page.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        PdfInfo with page count, size and extractability status
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ImportError: If pdfplumber is not installed
        Exception: If PDF is corrupted or unreadable
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError(
            "pdfplumber is required. Install: pip install pdfplumber"
        )
    
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    file_size_bytes = pdf_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    logger.info(f"Inspecting PDF: {pdf_path} ({file_size_mb:.2f} MB)")
    
    # Open PDF without loading all content
    with pdfplumber.open(str(pdf_path)) as pdf:
        page_count = len(pdf.pages)
        
        # Check if text is extractable (test first page)
        is_text_extractable = False
        if page_count > 0:
            try:
                first_page = pdf.pages[0]
                sample_text = first_page.extract_text()
                is_text_extractable = bool(sample_text and sample_text.strip())
            except Exception as e:
                logger.warning(f"Could not extract text from first page: {e}")
                is_text_extractable = False
    
    info = PdfInfo(
        page_count=page_count,
        file_size_mb=file_size_mb,
        is_text_extractable=is_text_extractable,
        file_path=str(pdf_path),
    )
    
    logger.info(
        f"PDF inspection complete: {page_count} pages, "
        f"text_extractable={is_text_extractable}"
    )
    
    return info


def is_large_pdf(pdf_path: str | Path, threshold_mb: float = 50.0) -> bool:
    """
    Check if PDF is considered large.
    
    Args:
        pdf_path: Path to PDF file
        threshold_mb: Size threshold in MB (default 50)
        
    Returns:
        True if file size exceeds threshold
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return False
    
    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    return size_mb > threshold_mb
