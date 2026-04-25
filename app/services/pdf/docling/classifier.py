"""
Page type classifier based on Docling document structure.

Determines if page contains:
- Table (structured product data)
- Gallery (images with SKUs)
- Text only
- Mixed content
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .models import PageType

if TYPE_CHECKING:
    from docling.datamodel.document import DoclingDocument

logger = logging.getLogger(__name__)


class PageClassifier:
    """
    Classifies PDF pages by content type.
    
    Uses Docling's hierarchical document model to detect:
    - Tables with product data
    - Pictures/images (gallery pages)
    - Text structure
    """
    
    def __init__(self):
        self.table_indicators = [
            "артикул", "код", "sku", "модель", "размер",
            "цена", "стоимость", "ед.изм", "шт", "компл"
        ]
    
    def classify_page(
        self,
        doc: "DoclingDocument",
        page_number: int
    ) -> PageType:
        """
        Classify single page from Docling document.
        
        Args:
            doc: Parsed Docling document
            page_number: 1-based page number
            
        Returns:
            PageType classification
        """
        # Get items for this page
        tables = self._get_tables_on_page(doc, page_number)
        pictures = self._get_pictures_on_page(doc, page_number)
        text_items = self._get_text_on_page(doc, page_number)
        
        has_table = len(tables) > 0
        has_pictures = len(pictures) > 0
        has_text = len(text_items) > 0
        
        # Classification logic
        if not has_table and not has_pictures and not has_text:
            return PageType.EMPTY
        
        # Table page: has table with product indicators
        if has_table:
            if self._is_product_table(tables[0]):
                return PageType.TABLE
        
        # Gallery page: has pictures + some text (captions)
        if has_pictures and len(pictures) >= 2:
            # Multiple images likely = gallery
            if has_text or self._has_caption_like_text(text_items):
                return PageType.GALLERY
        
        # Mixed: has both table and pictures
        if has_table and has_pictures:
            return PageType.MIXED
        
        # Text only
        if has_text and not has_table and not has_pictures:
            return PageType.TEXT
        
        # Default: mixed or text
        return PageType.MIXED if has_pictures else PageType.TEXT
    
    def _get_tables_on_page(
        self,
        doc: "DoclingDocument",
        page_number: int
    ) -> list:
        """Extract tables that appear on given page."""
        tables = []
        try:
            for table in doc.tables:
                # Check if table is on this page
                if hasattr(table, 'prov') and table.prov:
                    for prov in table.prov:
                        if getattr(prov, 'page_no', None) == page_number:
                            tables.append(table)
                            break
        except Exception as e:
            logger.debug(f"Error getting tables: {e}")
        return tables
    
    def _get_pictures_on_page(
        self,
        doc: "DoclingDocument",
        page_number: int
    ) -> list:
        """Extract pictures that appear on given page."""
        pictures = []
        try:
            for picture in doc.pictures:
                if hasattr(picture, 'prov') and picture.prov:
                    for prov in picture.prov:
                        if getattr(prov, 'page_no', None) == page_number:
                            pictures.append(picture)
                            break
        except Exception as e:
            logger.debug(f"Error getting pictures: {e}")
        return pictures
    
    def _get_text_on_page(
        self,
        doc: "DoclingDocument",
        page_number: int
    ) -> list:
        """Extract text items for page."""
        texts = []
        try:
            for item in doc.texts:
                if hasattr(item, 'prov') and item.prov:
                    for prov in item.prov:
                        if getattr(prov, 'page_no', None) == page_number:
                            texts.append(item)
                            break
        except Exception as e:
            logger.debug(f"Error getting texts: {e}")
        return texts
    
    def _is_product_table(self, table) -> bool:
        """Check if table looks like product catalog table."""
        try:
            # Get table text/content
            table_text = ""
            if hasattr(table, 'data') and table.data:
                for row in table.data[:3]:  # Check first 3 rows
                    for cell in row:
                        table_text += " " + str(cell).lower()
            
            # Check for product indicators
            indicators_found = sum(
                1 for ind in self.table_indicators if ind in table_text
            )
            return indicators_found >= 2  # At least 2 indicators
            
        except Exception:
            return False
    
    def _has_caption_like_text(self, text_items: list) -> bool:
        """Check if texts look like image captions (short, below images)."""
        if not text_items:
            return False
        
        # Captions are usually short
        short_texts = [
            t for t in text_items
            if len(str(getattr(t, 'text', ''))) < 100
        ]
        return len(short_texts) >= len(text_items) * 0.5
