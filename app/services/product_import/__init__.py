"""Product import services for safe bulk import with deduplication.

Handles import from PDF-extracted products with dry-run support,
conflict resolution, and automatic brand overrides.

Brand Overrides Integration:
- After any import, brand overrides from product_brand_overrides table
  are automatically applied
- Pipeline fails if any products still have NULL brand after overrides
"""

from .normalizer import (
    build_product_payload,
    product_identity_key,
    normalize_text,
    normalize_text_for_comparison,
    normalize_sku,
)
from .dedup import deduplicate_items_locally, ProductIdentity
from .importer import ProductImporter, ImportResult
from .brand_overrides_service import (
    BrandOverridesService,
    BrandOverridesResult,
    BrandOverridesAuditError,
    finalize_import_with_brand_overrides,
)
from .finalize_service import finalize_import

__all__ = [
    # Brand overrides
    "BrandOverridesService",
    "BrandOverridesResult",
    "BrandOverridesAuditError",
    "finalize_import_with_brand_overrides",
    "finalize_import",
    "build_product_payload",
    "product_identity_key",
    "normalize_text",
    "normalize_text_for_comparison",
    "normalize_sku",
    "deduplicate_items_locally",
    "ProductIdentity",
    "ProductImporter",
    "ImportResult",
]
