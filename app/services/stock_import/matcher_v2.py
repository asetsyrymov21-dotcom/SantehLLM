"""V2 Stock import matcher with fixed CSV export."""

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass  
class MatchResult:
    """Result of matching a single row."""

    row_index: int
    raw_sku: Optional[str]
    normalized_sku: Optional[str]
    raw_qty: any
    parsed_qty: any
    product_id: Optional[int]
    match_status: str
    brand_derived: Optional[str]
    sheet_name: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict:
        """Convert to dict for reporting with correct field mapping."""
        return {
            "sku_raw": self.raw_sku or "",
            "sku_normalized": self.normalized_sku or "",
            "sheet_name": self.sheet_name or "",
            "source_row": self.row_index,
            "qty_raw": str(self.raw_qty) if self.raw_qty is not None else "",
            "qty_parsed": self.parsed_qty.stock_label if self.parsed_qty else "",
            "qty_status": self.parsed_qty.parse_status if self.parsed_qty else "",
            "product_id": self.product_id or "",
            "brand": self.brand_derived or "",
            "status": self.match_status,
            "notes": "; ".join(self.notes) if self.notes else "",
        }


@dataclass
class UnmatchedSkuReport:
    """Detailed report for unmatched SKUs."""

    unmatched_results: list
    generated_at: datetime

    def to_csv_v2(self, filepath: Path) -> Path:
        """Export unmatched SKUs to CSV using to_report_dict()."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[to_csv_v2] Starting export of {len(self.unmatched_results)} rows to {filepath}")
        
        if not self.unmatched_results:
            logger.warning("[to_csv_v2] No unmatched results to export!")
            # Still create empty file with headers
            pass
            
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Get fieldnames from first result's to_report_dict
        if self.unmatched_results:
            sample_dict = self.unmatched_results[0].to_report_dict()
            fieldnames = list(sample_dict.keys())
            logger.info(f"[to_csv_v2] Fieldnames from to_report_dict: {fieldnames}")
        else:
            fieldnames = [
                "sku_raw", "sku_normalized", "sheet_name", "source_row",
                "qty_raw", "qty_parsed", "qty_status", "product_id",
                "brand", "status", "notes"
            ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            rows_written = 0
            for r in self.unmatched_results:
                row_dict = r.to_report_dict()
                writer.writerow(row_dict)
                rows_written += 1
                
        logger.info(f"[to_csv_v2] Successfully wrote {rows_written} rows to {filepath}")
        return filepath