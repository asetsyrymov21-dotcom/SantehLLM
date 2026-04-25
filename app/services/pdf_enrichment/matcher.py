"""
SKU Matcher for PDF catalogs.

Finds products in PDF files by SKU matching.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from app.services.pdf.extractor import (
    extract_text_from_page,
    extract_table_from_page,
    extract_product_block_from_page,
)
from app.services.pdf.normalizer import normalize_sku, normalize_text

from .models import PdfProductMatch

logger = logging.getLogger(__name__)


class PdfSkuMatcher:
    """Matches SKUs across PDF catalog files."""
    
    def __init__(self, pdf_paths: list[Path | str]):
        """
        Initialize matcher with PDF catalog files.
        
        Args:
            pdf_paths: List of paths to PDF catalog files
        """
        self.pdf_paths = [Path(p) for p in pdf_paths]
        self._validate_pdfs()
        
        # Cache for extracted data
        self._page_cache: dict[tuple[str, int], dict[str, Any]] = {}
    
    def _validate_pdfs(self) -> None:
        """Validate that PDF files exist."""
        for pdf_path in self.pdf_paths:
            if not pdf_path.exists():
                logger.warning(f"PDF not found: {pdf_path}")
    
    def find_sku(self, target_sku: str) -> Optional[PdfProductMatch]:
        """
        Find product by SKU across all PDF catalogs.
        
        Args:
            target_sku: SKU to search for
            
        Returns:
            PdfProductMatch if found, None otherwise
        """
        normalized_target = normalize_sku(target_sku)
        logger.debug(f"Searching for SKU: {target_sku} (normalized: {normalized_target})")
        
        for pdf_path in self.pdf_paths:
            if not pdf_path.exists():
                continue
                
            match = self._find_sku_in_pdf(pdf_path, normalized_target)
            if match:
                logger.info(f"Found SKU {target_sku} in {pdf_path.name}, page {match.source_page}")
                return match
        
        logger.debug(f"SKU {target_sku} not found in any PDF")
        return None
    
    def _find_sku_in_pdf(
        self, 
        pdf_path: Path, 
        normalized_sku: str
    ) -> Optional[PdfProductMatch]:
        """
        Search for SKU in a single PDF file.
        
        Strategy:
        1. Try to extract product blocks (structured pages with titles)
        2. Fall back to table extraction
        3. Last resort: text search
        """
        import pdfplumber
        
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                total_pages = len(pdf.pages)
                
                for page_num in range(1, total_pages + 1):
                    try:
                        # Try structured product block extraction first
                        match = self._try_product_block_match(
                            pdf_path, page_num, normalized_sku
                        )
                        if match:
                            return match
                        
                        # Fall back to table extraction
                        match = self._try_table_match(
                            pdf_path, page_num, normalized_sku
                        )
                        if match:
                            return match
                            
                    except Exception as e:
                        logger.debug(f"Error processing page {page_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.warning(f"Error opening PDF {pdf_path}: {e}")
        
        return None
    
    def _try_product_block_match(
        self,
        pdf_path: Path,
        page_num: int,
        normalized_sku: str
    ) -> Optional[PdfProductMatch]:
        """Try to find SKU in a structured product block."""
        try:
            block = extract_product_block_from_page(
                pdf_path, 
                page_num,
                source_file=pdf_path.name
            )
            
            if not block or not block.rows:
                return None
            
            # Search for SKU in rows
            for row in block.rows:
                row_sku = row.get("sku") or row.get("артикул") or ""
                if not row_sku:
                    continue
                    
                normalized_row_sku = normalize_sku(str(row_sku))
                
                if normalized_row_sku == normalized_sku:
                    # Build description from row data
                    description_parts = []
                    for key, value in row.items():
                        if key not in ("sku", "артикул") and value:
                            description_parts.append(f"{key}: {value}")
                    
                    return PdfProductMatch(
                        sku=normalized_sku,
                        pdf_title=block.title or "",
                        pdf_subtitle=block.subtitle or None,
                        pdf_description="\n".join(description_parts) if description_parts else None,
                        source_file=pdf_path.name,
                        source_page=page_num,
                        additional_attributes=dict(row)
                    )
                    
        except Exception as e:
            logger.debug(f"Product block extraction failed for page {page_num}: {e}")
        
        return None
    
    def _try_table_match(
        self,
        pdf_path: Path,
        page_num: int,
        normalized_sku: str
    ) -> Optional[PdfProductMatch]:
        """Try to find SKU in tables."""
        try:
            tables = extract_table_from_page(pdf_path, page_num)
            
            for row in tables:
                # Look for SKU-like column
                sku_value = None
                sku_col = None
                
                for key, value in row.items():
                    if not value:
                        continue
                    
                    normalized_value = normalize_sku(str(value))
                    if normalized_value == normalized_sku:
                        sku_value = normalized_value
                        sku_col = key
                        break
                
                if sku_value:
                    # Build title from page context
                    text = extract_text_from_page(pdf_path, page_num)
                    title = self._extract_title_from_page_text(text)
                    
                    # Build description from other columns
                    description_parts = []
                    for key, value in row.items():
                        if key != sku_col and value:
                            description_parts.append(f"{key}: {value}")
                    
                    return PdfProductMatch(
                        sku=normalized_sku,
                        pdf_title=title or "",
                        pdf_description="\n".join(description_parts) if description_parts else None,
                        source_file=pdf_path.name,
                        source_page=page_num,
                        additional_attributes=dict(row)
                    )
                    
        except Exception as e:
            logger.debug(f"Table extraction failed for page {page_num}: {e}")
        
        return None
    
    def _extract_title_from_page_text(self, text: str) -> Optional[str]:
        """Extract product title from page text."""
        if not text:
            return None
        
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        
        # Look for title patterns
        # Usually title is at the top, contains product type, not too short
        for line in lines[:10]:  # Check first 10 lines
            line = normalize_text(line)
            
            # Skip noise
            if self._is_noise_line(line):
                continue
            
            # Look for product indicators
            if any(indicator in line.lower() for indicator in [
                "смеситель", "кран", "вал", "труба", "угол", "фитинг",
                "гибка", "колено", "переход", "заглушка", "муфта"
            ]):
                if len(line) > 10 and len(line) < 200:
                    return line
        
        # Fallback: return first substantial line
        for line in lines[:5]:
            line = normalize_text(line)
            if len(line) > 15 and len(line) < 150:
                return line
        
        return None
    
    def _is_noise_line(self, line: str) -> bool:
        """Check if line is noise (page numbers, headers, etc)."""
        noise_patterns = [
            r"^\s*\d+\s*$",  # Just numbers
            r"^стр\.?\s*\d+",  # Page numbers
            r"^page\s*\d+",  # Page in English
            r"^каталог",  # Catalog header
            r"^www\.",  # URLs
            r"^http",  # URLs
        ]
        
        for pattern in noise_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        
        return False


class CachedPdfSkuMatcher(PdfSkuMatcher):
    """SKU matcher with caching for repeated lookups."""
    
    def __init__(self, pdf_paths: list[Path | str]):
        super().__init__(pdf_paths)
        self._sku_cache: dict[str, Optional[PdfProductMatch]] = {}
    
    def find_sku(self, target_sku: str) -> Optional[PdfProductMatch]:
        """Find SKU with caching."""
        normalized_target = normalize_sku(target_sku)
        
        if normalized_target in self._sku_cache:
            return self._sku_cache[normalized_target]
        
        result = super().find_sku(target_sku)
        self._sku_cache[normalized_target] = result
        return result
