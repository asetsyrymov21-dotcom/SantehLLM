#!/usr/bin/env python3
"""CLI script to apply brand overrides and audit.

Usage:
    python scripts/apply_brand_overrides.py --dry-run
    python scripts/apply_brand_overrides.py --commit
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.services.product_import.brand_overrides_service import (
    BrandOverridesService,
    BrandOverridesAuditError,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply brand overrides from product_brand_overrides table")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Show what would be changed")
    parser.add_argument("--commit", action="store_true", help="Actually apply changes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = not args.commit
    
    session = SessionLocal()
    try:
        service = BrandOverridesService(session)
        
        if dry_run:
            logger.info("DRY RUN MODE - checking what would be changed...")
            result = service.apply_overrides_silent()
            logger.info(f"Would update: {result.updated_rows} rows")
            logger.info(f"NULL brands after: {result.total_brand_null}")
            if result.success:
                logger.info("AUDIT PASSED: No NULL brands after overrides")
            else:
                logger.warning(f"AUDIT WOULD FAIL: {result.error_message}")
            return 0
        
        logger.info("COMMIT MODE - applying brand overrides...")
        try:
            result = service.apply_overrides()
            session.commit()
            logger.info("SUCCESS!")
            logger.info(f"Updated rows: {result.updated_rows}")
            logger.info(f"NULL brands: {result.total_brand_null}")
            return 0
        except BrandOverridesAuditError as e:
            session.rollback()
            logger.error(f"AUDIT FAILED: {e}")
            logger.error(f"Updated rows before failure: {e.updated_rows}")
            logger.error(f"NULL brand count: {e.null_count}")
            logger.error("Fix: Add missing SKUs to product_brand_overrides table")
            return 1
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())