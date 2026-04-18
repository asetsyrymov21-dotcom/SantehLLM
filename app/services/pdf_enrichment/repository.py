"""
Repository for saved PDF data.

Provides access to pre-built PDF text dumps and SKU indexes.
Replaces live PDF scanning in enrichment flow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .models import PdfPageDump, PdfTextDump, SkuIndex
from .bootstrap import load_pdf_dump, load_sku_index

logger = logging.getLogger(__name__)


class SavedPdfRepository:
    """Repository for accessing saved PDF data (dump + index).
    
    This class replaces live PDF scanning by loading pre-built
    text dumps and SKU indexes from JSON files.
    
    Usage:
        repo = SavedPdfRepository(dump_path="pages.json", index_path="index.json")
        if repo.load():
            pages = repo.get_candidate_pages("G10101")
            for page_num in pages:
                page_data = repo.get_page(page_num)
                # Process page_data.raw_text
    """
    
    def __init__(
        self,
        dump_path: Path | str,
        index_path: Path | str,
        pdf_name: Optional[str] = None,
    ):
        """Initialize repository with paths to saved data.
        
        Args:
            dump_path: Path to the JSON dump file (page texts)
            index_path: Path to the JSON index file (sku -> pages)
            pdf_name: Optional name of the PDF for logging
        """
        self.dump_path = Path(dump_path)
        self.index_path = Path(index_path)
        self.pdf_name = pdf_name or self.dump_path.stem
        
        self._dump: Optional[PdfTextDump] = None
        self._index: Optional[SkuIndex] = None
        self._page_map: dict[int, PdfPageDump] = {}
    
    def load(self) -> bool:
        """Load dump and index from JSON files.
        
        Returns:
            True if both files loaded successfully
        """
        logger.info(f"Loading saved PDF data for '{self.pdf_name}'")
        
        if not self.dump_path.exists():
            raise FileNotFoundError(f"Dump file not found: {self.dump_path}")
        if not self.index_path.exists():
            raise FileNotFoundError(f"Index file not found: {self.index_path}")
        
        self._dump = load_pdf_dump(self.dump_path)
        self._index = load_sku_index(self.index_path)
        
        # Build page lookup map
        self._page_map = {page.page_number: page for page in self._dump.pages}
        
        logger.info(
            f"Loaded {len(self._page_map)} pages, "
            f"{len(self._index.sku_to_pages)} SKUs indexed"
        )
        
        return True
    
    def has_data(self) -> bool:
        """Check if data is loaded."""
        return self._dump is not None and self._index is not None
    
    def get_candidate_pages(self, sku: str) -> list[int]:
        """Get candidate page numbers where SKU might be found.
        
        Args:
            sku: SKU to search for
            
        Returns:
            List of page numbers (1-indexed), sorted
        """
        if not self._index:
            logger.warning("Repository not loaded, call load() first")
            return []
        
        pages = self._index.get_pages_for_sku(sku)
        return sorted(set(pages))
    
    def get_page(self, page_number: int) -> Optional[PdfPageDump]:
        """Get page dump by page number.
        
        Args:
            page_number: 1-indexed page number
            
        Returns:
            PdfPageDump if found, None otherwise
        """
        if not self._page_map:
            logger.warning("Repository not loaded, call load() first")
            return None
        
        return self._page_map.get(page_number)
    
    def get_page_text(self, page_number: int) -> str:
        """Get raw text for a specific page.
        
        Args:
            page_number: 1-indexed page number
            
        Returns:
            Raw page text, or empty string if not found
        """
        page = self.get_page(page_number)
        return page.raw_text if page else ""
    
    def get_all_skus(self) -> list[str]:
        """Get all SKUs in the index."""
        if not self._index:
            return []
        return list(self._index.sku_to_pages.keys())
    
    def get_page_count(self) -> int:
        """Get total number of pages."""
        return len(self._page_map) if self._page_map else 0
    
    def sku_exists(self, sku: str) -> bool:
        """Check if SKU exists in index."""
        if not self._index:
            return False
        return len(self._index.get_pages_for_sku(sku)) > 0


class MultiPdfRepository:
    """Repository that aggregates multiple SavedPdfRepository instances."""
    
    def __init__(self):
        self._repositories: list[SavedPdfRepository] = []
    
    def add_repository(self, repo: SavedPdfRepository) -> None:
        """Add a repository to the aggregate."""
        self._repositories.append(repo)
    
    def load_all(self) -> bool:
        """Load all repositories."""
        for repo in self._repositories:
            if not repo.has_data():
                repo.load()
        return all(repo.has_data() for repo in self._repositories)
    
    def has_data(self) -> bool:
        """Check if any repository has data."""
        return any(repo.has_data() for repo in self._repositories)
    
    def get_candidate_pages(self, sku: str) -> list[tuple[str, int]]:
        """Get candidate pages from all repositories.
        
        Returns:
            List of (pdf_name, page_number) tuples
        """
        results = []
        for repo in self._repositories:
            pages = repo.get_candidate_pages(sku)
            for page in pages:
                results.append((repo.pdf_name, page))
        return results
    
    def get_page(self, pdf_name: str, page_number: int) -> Optional[PdfPageDump]:
        """Get page from specific PDF."""
        for repo in self._repositories:
            if repo.pdf_name == pdf_name:
                return repo.get_page(page_number)
        return None