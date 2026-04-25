"""
Docling-based PDF extractor with page-by-page processing.

Handles large PDFs efficiently using Docling's streaming capabilities.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .models import ExtractionResult, PageType, TableRow, ImageItem
from .classifier import PageClassifier

try:
    from docling.datamodel.document import DoclingDocument
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    DoclingDocument = None
    InputFormat = None
    DocumentConverter = None

logger = logging.getLogger(__name__)


class DoclingExtractor:
    """
    Extracts product data from PDF using Docling.
    
    Handles both table pages and gallery pages.
    Processes one page at a time to save memory.
    """
    
    def __init__(self):
        if not DOCLING_AVAILABLE:
            raise ImportError(
                "Docling not installed. "
                "Run: pip install -r requirements-docling.txt"
            )
        
        self.converter = DocumentConverter()
        self.classifier = PageClassifier()
    
    def extract_page(
        self,
        pdf_path: str | Path,
        page_number: int,
        brand_hint: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract single page from PDF.
        
        Args:
            pdf_path: Path to PDF file
            page_number: 1-based page number
            brand_hint: Optional brand name
            
        Returns:
            ExtractionResult with typed content
        """
        start_time = time.time()
        pdf_path = Path(pdf_path)
        
        logger.info(f"Processing page {page_number} from {pdf_path.name}")
        
        # Convert single page
        doc = self._convert_single_page(pdf_path, page_number)
        if not doc:
            return ExtractionResult(
                page_number=page_number,
                page_type=PageType.EMPTY,
                source_file=pdf_path.name,
            )
        
        # Classify page
        page_type = self.classifier.classify_page(doc, page_number)
        
        # Extract based on type
        result = ExtractionResult(
            page_number=page_number,
            page_type=page_type,
            brand_hint=brand_hint,
            source_file=pdf_path.name,
            processing_time_ms=(time.time() - start_time) * 1000,
        )
        
        if page_type == PageType.TABLE:
            result = self._extract_table_page(doc, page_number, result)
        elif page_type == PageType.GALLERY:
            result = self._extract_gallery_page(doc, page_number, result)
        else:
            result = self._extract_text_page(doc, page_number, result)
        
        # Log item types found (for debugging)
        result.docling_items = self._get_item_types(doc, page_number)
        
        return result
    
    def extract_pages(
        self,
        pdf_path: str | Path,
        page_numbers: list[int],
        brand_hint: Optional[str] = None,
    ) -> list[ExtractionResult]:
        """
        Extract multiple pages efficiently.
        
        Args:
            pdf_path: Path to PDF
            page_numbers: List of 1-based page numbers
            brand_hint: Optional brand
            
        Returns:
            List of ExtractionResult
        """
        results = []
        for page_num in page_numbers:
            try:
                result = self.extract_page(pdf_path, page_num, brand_hint)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to extract page {page_num}: {e}")
                results.append(ExtractionResult(
                    page_number=page_num,
                    page_type=PageType.EMPTY,
                    source_file=str(pdf_path),
                ))
        return results
    
    def _convert_single_page(
        self,
        pdf_path: Path,
        page_number: int
    ) -> Optional["DoclingDocument"]:
        """Convert single page to Docling document."""
        try:
            # Docling converts full doc but we process per-page
            result = self.converter.convert(str(pdf_path))
            return result.document
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return None
    
    def _extract_table_page(
        self,
        doc: "DoclingDocument",
        page_number: int,
        result: ExtractionResult,
    ) -> ExtractionResult:
        """Extract data from table page."""
        tables = self.classifier._get_tables_on_page(doc, page_number)
        
        if not tables:
            return result
        
        table = tables[0]  # Use first table
        
        # Extract headers
        if hasattr(table, 'data') and table.data:
            headers = [str(h).strip() for h in table.data[0]] if table.data else []
            result.table_headers = headers
            
            # Extract rows
            for row_data in table.data[1:]:  # Skip header
                cells = {}
                for idx, cell in enumerate(row_data):
                    header = headers[idx] if idx < len(headers) else f"col_{idx}"
                    cells[header] = str(cell).strip() if cell else None
                
                # Try to find SKU
                sku = self._extract_sku_from_cells(cells)
                
                result.table_rows.append(TableRow(
                    sku=sku,
                    cells=cells,
                    raw_text=" | ".join(str(c) for c in row_data if c),
                ))
        
        # Try to find title from text
        result.title = self._find_title_on_page(doc, page_number)
        
        return result
    
    def _extract_gallery_page(
        self,
        doc: "DoclingDocument",
        page_number: int,
        result: ExtractionResult,
    ) -> ExtractionResult:
        """Extract data from gallery page (images with captions)."""
        pictures = self.classifier._get_pictures_on_page(doc, page_number)
        texts = self.classifier._get_text_on_page(doc, page_number)
        
        # Match pictures with nearby text
        for idx, picture in enumerate(pictures):
            caption = self._find_caption_for_picture(picture, texts)
            sku = self._extract_sku_from_text(caption) if caption else None
            
            result.image_items.append(ImageItem(
                image_index=idx,
                caption=caption[:200] if caption else "",
                sku=sku,
                surrounding_text=self._get_surrounding_text(picture, texts),
            ))
        
        result.title = self._find_title_on_page(doc, page_number)
        
        return result
    
    def _extract_text_page(
        self,
        doc: "DoclingDocument",
        page_number: int,
        result: ExtractionResult,
    ) -> ExtractionResult:
        """Extract data from text-only page."""
        texts = self.classifier._get_text_on_page(doc, page_number)
        result.raw_text = "\n".join(
            str(getattr(t, 'text', '')) for t in texts
        )
        result.title = self._find_title_on_page(doc, page_number)
        return result
    
    def _get_item_types(
        self,
        doc: "DoclingDocument",
        page_number: int
    ) -> list[str]:
        """Get list of Docling item types on page (for debugging)."""
        types = []
        try:
            for item in doc.iterate_items():
                item_type = type(item).__name__
                types.append(item_type)
        except Exception:
            pass
        return list(set(types))[:10]  # Unique types, limit 10
    
    def _extract_sku_from_cells(self, cells: dict) -> Optional[str]:
        """Find SKU in table cells."""
        sku_keys = ['артикул', 'код', 'sku', 'модель', 'model', 'code']
        for key in sku_keys:
            for k, v in cells.items():
                if key in k.lower() and v:
                    return str(v).strip()
        return None
    
    def _extract_sku_from_text(self, text: str) -> Optional[str]:
        """Extract SKU pattern from text."""
        if not text:
            return None
        # Common patterns: F123.456, ABC-1234, etc.
        import re
        patterns = [
            r'([A-Z]\d{3}[\.-]\d{3,4})',  # F123.456
            r'([A-Z]{2,4}-\d{3,6})',       # FRAP-1234
            r'(\d{6,})',                    # 123456
        ]
        for pattern in patterns:
            match = re.search(pattern, text.upper())
            if match:
                return match.group(1)
        return None
    
    def _find_title_on_page(
        self,
        doc: "DoclingDocument",
        page_number: int
    ) -> Optional[str]:
        """Find page title (usually first heading)."""
        texts = self.classifier._get_text_on_page(doc, page_number)
        if not texts:
            return None
        
        # First substantial text is likely title
        for text_item in texts:
            text = str(getattr(text_item, 'text', '')).strip()
            if len(text) > 5 and len(text) < 200:
                return text
        return None
    
    def _find_caption_for_picture(self, picture, texts: list) -> str:
        """Find caption text below or near picture."""
        # Simple heuristic: find short text items
        captions = []
        for text_item in texts:
            text = str(getattr(text_item, 'text', '')).strip()
            if 5 < len(text) < 150:  # Caption length
                captions.append(text)
        return captions[0] if captions else ""
    
    def _get_surrounding_text(self, picture, texts: list) -> str:
        """Get context text around picture."""
        # Return first few text items as context
        return " ".join(
            str(getattr(t, 'text', ''))[:50] 
            for t in texts[:3]
        )
