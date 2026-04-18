"""Unmatched SKU analyzer for FRAP stock import.

Analyzes unmatched SKUs to determine probable reasons for mismatch.
This is a separate analysis tool - does not modify import logic.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository
from app.utils.sku_utils import normalize_sku

logger = logging.getLogger(__name__)


@dataclass
class UnmatchedSkuAnalysis:
    """Analysis result for a single unmatched SKU."""
    
    source_sku: str
    normalized_sku: str
    source_row: int
    qty_raw: str
    
    # Analysis results
    probable_reason: str  # real_missing, format_mismatch, family_or_variant_match, etc.
    confidence: str  # high, medium, low
    
    # Match candidates
    matched_catalog_sku: Optional[str] = None
    matched_product_id: Optional[int] = None
    candidate_count: int = 0
    
    # Additional info
    notes: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "source_sku": self.source_sku,
            "normalized_sku": self.normalized_sku,
            "source_row": self.source_row,
            "qty_raw": self.qty_raw,
            "probable_reason": self.probable_reason,
            "confidence": self.confidence,
            "matched_catalog_sku": self.matched_catalog_sku or "",
            "matched_product_id": self.matched_product_id or "",
            "candidate_count": self.candidate_count,
            "notes": "; ".join(self.notes) if self.notes else "",
        }


@dataclass  
class UnmatchedAnalysisSummary:
    """Summary of unmatched SKU analysis."""
    
    total_analyzed: int = 0
    real_missing: int = 0
    format_mismatch: int = 0
    family_or_variant_match: int = 0
    ambiguous_match: int = 0
    duplicate_catalog_candidate: int = 0
    unknown: int = 0
    
    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("UNMATCHED SKU ANALYSIS SUMMARY")
        print("=" * 60)
        print(f"Total analyzed: {self.total_analyzed}")
        print("-" * 60)
        print(f"  Real missing:           {self.real_missing}")
        print(f"  Format mismatch:        {self.format_mismatch}")
        print(f"  Family/variant match:   {self.family_or_variant_match}")
        print(f"  Ambiguous match:        {self.ambiguous_match}")
        print(f"  Duplicate catalog cand: {self.duplicate_catalog_candidate}")
        print(f"  Unknown:                {self.unknown}")
        print("=" * 60)


class SkuVariantChecker:
    """Checks for format variants of a SKU."""
    
    VARIANT_TRANSFORMS = [
        ("original", lambda x: x),
        ("trim", lambda x: x.strip()),
        ("uppercase", lambda x: x.upper()),
        ("lowercase", lambda x: x.lower()),
        ("no_spaces", lambda x: x.replace(" ", "")),
        ("unicode_dash_to_ascii", lambda x: x.replace("—", "-").replace("–", "-")),
        ("no_spaces_around_dash", lambda x: x.replace(" - ", "-").replace("- ", "-").replace(" -", "-")),
        ("collapse_dashes", lambda x: re.sub(r"-+", "-", x)),
        ("strip_trailing_dotzero", lambda x: re.sub(r"\.0+$", "", x)),
        ("remove_all_spaces", lambda x: "".join(x.split())),
    ]
    
    def get_variants(self, sku: str) -> dict[str, str]:
        """Generate all format variants of a SKU."""
        variants = {}
        for name, transform in self.VARIANT_TRANSFORMS:
            try:
                variant = transform(sku)
                if variant and variant != sku:
                    variants[name] = variant
            except Exception:
                continue
        return variants


class UnmatchedSkuAnalyzer:
    """Analyzer for unmatched SKUs from stock import."""
    
    def __init__(self, session: Session):
        self.session = session
        self.product_repo = ProductRepository(session)
        self.variant_checker = SkuVariantChecker()
    
    def analyze_csv(self, csv_path: Path | str) -> tuple[list[UnmatchedSkuAnalysis], UnmatchedAnalysisSummary]:
        """Analyze unmatched SKUs from CSV file."""
        csv_path = Path(csv_path)
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        # Read CSV
        rows = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        
        logger.info(f"Loaded {len(rows)} unmatched SKUs from {csv_path}")
        
        # Analyze each row
        analyses = []
        for row in rows:
            analysis = self._analyze_single_row(row)
            analyses.append(analysis)
        
        # Build summary
        summary = self._build_summary(analyses)
        
        return analyses, summary
    
    def _analyze_single_row(self, row: dict[str, Any]) -> UnmatchedSkuAnalysis:
        """Analyze a single unmatched SKU."""
        
        source_sku = row.get("sku_raw", row.get("source_sku", ""))
        normalized_sku = row.get("sku_normalized", normalize_sku(source_sku))
        source_row = int(row.get("row", row.get("source_row", 0)))
        qty_raw = row.get("qty_raw", "")
        
        analysis = UnmatchedSkuAnalysis(
            source_sku=source_sku,
            normalized_sku=normalized_sku,
            source_row=source_row,
            qty_raw=qty_raw,
            probable_reason="unknown",
            confidence="low",
            notes=[],
        )
        
        # Step A: Exact recheck
        exact_match = self._exact_recheck(normalized_sku)
        if exact_match:
            analysis.probable_reason = "format_mismatch"
            analysis.confidence = "high"
            analysis.matched_catalog_sku = exact_match.sku
            analysis.matched_product_id = exact_match.id
            analysis.candidate_count = 1
            analysis.notes.append(f"Exact match found on recheck: {exact_match.sku}")
            return analysis
        
        # Step B: Format variants
        format_match, variant_name = self._check_format_variants(normalized_sku)
        if format_match:
            analysis.probable_reason = "format_mismatch"
            analysis.confidence = "high"
            analysis.matched_catalog_sku = format_match.sku
            analysis.matched_product_id = format_match.id
            analysis.candidate_count = 1
            analysis.notes.append(f"Format variant match ({variant_name}): {format_match.sku}")
            return analysis
        
        # Step C: Family/variant analysis
        family_result = self._analyze_family_match(normalized_sku)
        if family_result:
            analysis.probable_reason = family_result["reason"]
            analysis.confidence = family_result["confidence"]
            analysis.matched_catalog_sku = family_result.get("matched_sku")
            analysis.matched_product_id = family_result.get("matched_id")
            analysis.candidate_count = family_result.get("candidate_count", 0)
            analysis.notes.extend(family_result.get("notes", []))
            return analysis
        
        # Step D: Near candidates
        near_result = self._find_near_candidates(normalized_sku)
        if near_result and near_result.get("candidate_count", 0) > 0:
            analysis.probable_reason = near_result.get("reason", "ambiguous_match")
            analysis.confidence = "low"
            analysis.candidate_count = near_result.get("candidate_count", 0)
            analysis.notes.extend(near_result.get("notes", []))
            return analysis
        
        # Step E: Real missing
        analysis.probable_reason = "real_missing"
        analysis.confidence = "medium"
        analysis.notes.append("No matching candidates found in catalog")
        
        return analysis
    
    def _exact_recheck(self, normalized_sku: str) -> Optional[Any]:
        """Step A: Recheck exact normalized SKU in database."""
        if not normalized_sku:
            return None
        return self.product_repo.get_by_sku(normalized_sku)
    
    def _check_format_variants(self, normalized_sku: str) -> tuple[Optional[Any], Optional[str]]:
        """Step B: Check format variants of the SKU."""
        if not normalized_sku:
            return None, None
        
        variants = self.variant_checker.get_variants(normalized_sku)
        
        for variant_name, variant_sku in variants.items():
            # Normalize the variant
            normalized_variant = normalize_sku(variant_sku)
            if not normalized_variant:
                continue
                
            product = self.product_repo.get_by_sku(normalized_variant)
            if product:
                return product, variant_name
        
        return None, None
    
    def _analyze_family_match(self, normalized_sku: str) -> Optional[dict]:
        """Step C: Analyze family/variant relationships."""
        if not normalized_sku:
            return None
        
        # Extract base SKU (before first "-")
        base_sku = normalized_sku.split("-")[0].strip()
        if not base_sku:
            return None
        
        # Search for products with matching base
        candidates = self._search_by_base_sku(base_sku)
        
        if not candidates:
            return None
        
        # Check for exact base match
        exact_base_match = None
        for prod in candidates:
            if prod.sku == base_sku:
                exact_base_match = prod
                break
        
        if exact_base_match:
            # Found the base SKU, this is likely a variant
            return {
                "reason": "family_or_variant_match",
                "confidence": "high",
                "matched_sku": exact_base_match.sku,
                "matched_id": exact_base_match.id,
                "candidate_count": 1,
                "notes": [f"Base SKU match: {base_sku} (source was variant: {normalized_sku})"],
            }
        
        # Check if all candidates share the same base
        base_variants = [p for p in candidates if p.sku.startswith(base_sku + "-")]
        
        if len(base_variants) == 1:
            # Single variant found
            return {
                "reason": "family_or_variant_match",
                "confidence": "medium",
                "matched_sku": base_variants[0].sku,
                "matched_id": base_variants[0].id,
                "candidate_count": 1,
                "notes": [f"Single variant of base {base_sku}: {base_variants[0].sku}"],
            }
        elif len(base_variants) > 1:
            # Multiple variants - ambiguous
            return {
                "reason": "ambiguous_match",
                "confidence": "medium",
                "candidate_count": len(base_variants),
                "notes": [f"Multiple variants of base {base_sku}: {[p.sku for p in base_variants]}"],
            }
        
        return None
    
    def _find_near_candidates(self, normalized_sku: str) -> Optional[dict]:
        """Step D: Find near-match candidates (same family, close names)."""
        if not normalized_sku or len(normalized_sku) < 3:
            return None
        
        # Get first 3-5 chars as prefix for similarity search
        prefix = normalized_sku[:5] if len(normalized_sku) >= 5 else normalized_sku[:3]
        
        # Search for products with similar prefix
        candidates = self._search_by_prefix(prefix)
        
        if len(candidates) > 1:
            return {
                "reason": "duplicate_catalog_candidate" if len(candidates) <= 3 else "ambiguous_match",
                "candidate_count": len(candidates),
                "notes": [f"Near candidates with prefix {prefix}: {[p.sku for p in candidates]}"],
            }
        
        return None
    
    def _search_by_base_sku(self, base_sku: str) -> list[Any]:
        """Search for products matching base SKU."""
        # Use repository to search
        products = []
        
        # Try exact match first
        exact = self.product_repo.get_by_sku(base_sku)
        if exact:
            products.append(exact)
        
        # Search for prefix matches
        try:
            # This assumes product_repo has a search method
            # Fallback: get all FRAP products and filter
            all_products = self._get_all_frap_products()
            for prod in all_products:
                if prod.sku.startswith(base_sku):
                    if prod not in products:
                        products.append(prod)
        except Exception as e:
            logger.warning(f"Search by base SKU failed: {e}")
        
        return products
    
    def _search_by_prefix(self, prefix: str) -> list[Any]:
        """Search for products with given prefix."""
        try:
            all_products = self._get_all_frap_products()
            return [p for p in all_products if p.sku.startswith(prefix)]
        except Exception as e:
            logger.warning(f"Search by prefix failed: {e}")
            return []
    
    def _get_all_frap_products(self) -> list[Any]:
        """Get all FRAP products."""
        try:
            # Use session query directly
            from app.db.models import Product
            return self.session.query(Product).filter(Product.brand == "FRAP").all()
        except Exception as e:
            logger.warning(f"Failed to get FRAP products: {e}")
            return []
    
    def _build_summary(self, analyses: list[UnmatchedSkuAnalysis]) -> UnmatchedAnalysisSummary:
        """Build summary from analyses."""
        summary = UnmatchedAnalysisSummary(total_analyzed=len(analyses))
        
        for analysis in analyses:
            reason = analysis.probable_reason
            if reason == "real_missing":
                summary.real_missing += 1
            elif reason == "format_mismatch":
                summary.format_mismatch += 1
            elif reason == "family_or_variant_match":
                summary.family_or_variant_match += 1
            elif reason == "ambiguous_match":
                summary.ambiguous_match += 1
            elif reason == "duplicate_catalog_candidate":
                summary.duplicate_catalog_candidate += 1
            else:
                summary.unknown += 1
        
        return summary
    
    def export_analysis_csv(
        self,
        analyses: list[UnmatchedSkuAnalysis],
        output_path: Path | str,
    ) -> Path:
        """Export analysis results to CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        fieldnames = [
            "source_sku",
            "normalized_sku",
            "source_row",
            "qty_raw",
            "probable_reason",
            "confidence",
            "matched_catalog_sku",
            "matched_product_id",
            "candidate_count",
            "notes",
        ]
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for analysis in analyses:
                writer.writerow(analysis.to_dict())
        
        logger.info(f"Exported analysis to: {output_path}")
        return output_path
