#!/usr/bin/env python3
"""Backfill product brand from SKU prefix.

Safe script with dry-run by default.
Only updates brand field, never changes other product data.

Usage:
    python scripts/backfill_brand_from_sku.py --dry-run
    python scripts/backfill_brand_from_sku.py --commit
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Product
from app.utils.sku_utils import derive_brand_from_sku, normalize_sku


@dataclass
class BrandBackfillStats:
    """Statistics for brand backfill operation."""
    total_checked: int = 0
    recognizable_prefix: int = 0
    fixes_planned: int = 0
    skipped: int = 0
    conflicts: int = 0
    updated: int = 0
    errors: int = 0

    # Details
    conflict_details: list[dict] = field(default_factory=list)

    def print_report(self, dry_run: bool = True) -> None:
        print("=" * 60)
        print("BRAND BACKFILL REPORT")
        if dry_run:
            print("MODE: DRY-RUN (no changes made)")
        else:
            print("MODE: COMMIT")
        print("=" * 60)
        print(f"Total products checked: {self.total_checked}")
        print(f"Products with recognizable prefix: {self.recognizable_prefix}")
        print(f"Brand fixes planned: {self.fixes_planned}")
        print(f"Skipped (already correct): {self.skipped}")
        print(f"Conflicts detected: {self.conflicts}")
        if not dry_run:
            print(f"Actually updated: {self.updated}")
            print(f"Errors: {self.errors}")
        print("=" * 60)

        if self.conflicts > 0:
            print("\n--- CONFLICTS (current brand != derived brand) ---")
            for conflict in self.conflicts_details[:20]:
                print(f"  SKU: {conflict['sku']}")
                print(f"    Current: {conflict['current_brand']}")
                print(f"    Derived: {conflict['derived_brand']}")
                print(f"    Action: {conflict['action']}")
            if len(self.conflicts_details) > 20:
                print(f"  ... and {len(self.conflicts_details) - 20} more conflicts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill product brand from SKU prefix (F* -> FRAP, G* -> GAPPO)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be changed without making changes (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually apply changes to database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of products to process (for testing)",
    )
    return parser.parse_args()


def process_products(session: Session, commit: bool = False, limit: Optional[int] = None) -> BrandBackfillStats:
    """Process all products and backfill brand from SKU."""
    stats = BrandBackfillStats()

    # Query all products
    query = select(Product)
    if limit:
        query = query.limit(limit)

    products = session.scalars(query).all()
    stats.total_checked = len(products)

    for product in products:
        # Normalize SKU
        normalized_sku = normalize_sku(product.sku)

        if not normalized_sku:
            stats.skipped += 1
            continue

        # Derive brand
        derived_brand = derive_brand_from_sku(normalized_sku)

        if not derived_brand:
            # No recognizable prefix
            stats.skipped += 1
            continue

        stats.recognizable_prefix += 1

        # Check current brand
        current_brand = product.brand

        if not current_brand:
            # No brand set - safe to update
            stats.fixes_planned += 1

            if commit:
                product.brand = derived_brand
                stats.updated += 1
                print(f"  SET: {product.sku} -> {derived_brand}")
            else:
                print(f"  WOULD SET: {product.sku} -> {derived_brand}")

        elif current_brand.upper() == derived_brand.upper():
            # Already correct
            stats.skipped += 1

        else:
            # CONFLICT!
            stats.conflicts += 1
            conflict = {
                "product_id": product.id,
                "sku": product.sku,
                "current_brand": current_brand,
                "derived_brand": derived_brand,
                "action": "SKIPPED (use --force-conflicts to override)" if not commit else "SKIPPED",
            }
            stats.conflicts_details.append(conflict)

            print(f"  CONFLICT: {product.sku}")
            print(f"    Current: {current_brand}")
            print(f"    Derived: {derived_brand}")

    return stats


def main() -> int:
    args = parse_args()

    # Determine mode
    commit = args.commit
    dry_run = not commit

    print(f"Starting brand backfill (commit={commit})...")

    session = SessionLocal()
    try:
        stats = process_products(session, commit=commit, limit=args.limit)

        if commit:
            try:
                session.commit()
                print("\nChanges committed successfully.")
            except Exception as e:
                session.rollback()
                print(f"\nCOMMIT FAILED: {e}", file=sys.stderr)
                return 1
        else:
            session.rollback()
            print("\nDry run completed - no changes made.")

        stats.print_report(dry_run=dry_run)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())