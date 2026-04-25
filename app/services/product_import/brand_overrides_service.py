"""Persistent brand overrides service for Santeh Catalog pipeline.

This service ensures that brand overrides from product_brand_overrides table
are automatically applied after any import, backfill, or repair operation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class BrandOverridesResult:
    """Result of applying brand overrides."""
    updated_rows: int
    total_brand_null: int
    success: bool
    error_message: str | None = None


# SQL to apply brand overrides from product_brand_overrides table
# Only updates rows where products.brand differs from product_brand_overrides.brand
APPLY_OVERRIDES_SQL = """
    UPDATE products p
    SET 
        brand = o.brand,
        updated_at = now()
    FROM product_brand_overrides o
    WHERE p.sku = o.sku
      AND coalesce(p.brand, '') <> o.brand
"""

# SQL to audit NULL brands after override application
AUDIT_NULL_BRANDS_SQL = """
    SELECT count(*) as total_brand_null
    FROM products
    WHERE brand IS NULL
"""


class BrandOverridesService:
    """Service for applying persistent brand overrides and auditing results."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def apply_overrides(self) -> BrandOverridesResult:
        """Apply brand overrides and audit the result.
        
        This method is idempotent - repeated calls are safe and will only
        update rows where products.brand differs from overrides.
        
        Returns:
            BrandOverridesResult with update count and audit results
            
        Raises:
            BrandOverridesAuditError: if any products still have NULL brand after overrides
        """
        # Step 1: Apply overrides
        updated_rows = self._execute_override_update()
        logger.info(f"[BRAND OVERRIDES] Applied {updated_rows} row(s) from product_brand_overrides")
        
        # Step 2: Audit - check for NULL brands
        null_count = self._execute_null_brand_audit()
        logger.info(f"[BRAND OVERRIDES] Audit complete: total_brand_null={null_count}")
        
        # Step 3: Fail if invariant violated
        if null_count > 0:
            error_msg = (
                f"BRAND OVERRIDE AUDIT FAILED: "
                f"{null_count} product(s) still have NULL brand after overrides. "
                f"Updated rows: {updated_rows}. "
                f"Check product_brand_overrides table for missing SKUs."
            )
            logger.error(f"[BRAND OVERRIDES] {error_msg}")
            raise BrandOverridesAuditError(error_msg, updated_rows, null_count)
        
        logger.info(
            f"[BRAND OVERRIDES] SUCCESS: "
            f"updated_rows={updated_rows}, total_brand_null={null_count}"
        )
        
        return BrandOverridesResult(
            updated_rows=updated_rows,
            total_brand_null=null_count,
            success=True
        )
    
    def _execute_override_update(self) -> int:
        """Execute the override update SQL and return count of affected rows."""
        result = self.session.execute(text(APPLY_OVERRIDES_SQL))
        return result.rowcount
    
    def _execute_null_brand_audit(self) -> int:
        """Execute the NULL brand audit SQL and return count."""
        result = self.session.execute(text(AUDIT_NULL_BRANDS_SQL))
        row = result.fetchone()
        return row[0] if row else 0
    
    def apply_overrides_silent(self) -> BrandOverridesResult:
        """Apply overrides without raising exception on audit failure.
        
        Use this for dry-run scenarios or when you need to handle failures manually.
        
        Returns:
            BrandOverridesResult with success=False if audit failed
        """
        try:
            return self.apply_overrides()
        except BrandOverridesAuditError as e:
            return BrandOverridesResult(
                updated_rows=e.updated_rows,
                total_brand_null=e.null_count,
                success=False,
                error_message=str(e)
            )


class BrandOverridesAuditError(Exception):
    """Raised when brand overrides audit detects NULL brands."""
    
    def __init__(self, message: str, updated_rows: int, null_count: int):
        super().__init__(message)
        self.updated_rows = updated_rows
        self.null_count = null_count


def finalize_import_with_brand_overrides(session: Session) -> BrandOverridesResult:
    """Convenience function to apply brand overrides after import.
    
    This is the main entry point for pipeline finalize steps.
    Should be called after any product import, backfill, or repair operation.
    
    Args:
        session: Database session
        
    Returns:
        BrandOverridesResult
        
    Raises:
        BrandOverridesAuditError: if audit invariant is violated
    """
    service = BrandOverridesService(session)
    return service.apply_overrides()