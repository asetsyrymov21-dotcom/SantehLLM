"""Finalize service for product import pipeline.

Applies brand overrides and audits the result after any import operation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .brand_overrides_service import (
    finalize_import_with_brand_overrides,
    BrandOverridesAuditError,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def finalize_import(session: Session, dry_run: bool = False):
    """Finalize import by applying brand overrides and auditing.

    Args:
        session: Database session
        dry_run: If True, only log without applying

    Returns:
        BrandOverridesResult or None if dry_run

    Raises:
        BrandOverridesAuditError: If audit invariant is violated
    """
    if dry_run:
        logger.info("[FINALIZE] Dry run - skipping brand overrides")
        return None

    logger.info("[FINALIZE] Applying brand overrides...")
    try:
        result = finalize_import_with_brand_overrides(session)
        logger.info(
            f"[FINALIZE] SUCCESS: updated_rows={result.updated_rows}, "
            f"total_brand_null={result.total_brand_null}"
        )
        return result
    except Exception as e:
        logger.error(f"[FINALIZE] FAILED: {e}")
        raise
