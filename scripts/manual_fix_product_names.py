from __future__ import annotations

import argparse

from app.db import SessionLocal, models


MANUAL_NAME_FIXES = {
    # Заполняй только после ручной проверки по PDF/source:
    # "G4398-1": "ПРОВЕРЕННОЕ_ИМЯ",
    # "G4398-16": "ПРОВЕРЕННОЕ_ИМЯ",
    "G4398-17": "Смеситель для кухни с подключением фильтра питьевой воды",
    "G4398-88": "Смеситель для кухни с подключением фильтра для воды",
    "G4398-89": "Смеситель для кухни с подключением фильтра для воды",
    "G4395-60": "Смеситель для кухни с подключением фильтра питьевой воды",
    "G4395-66": "Смеситель для кухни с подключением фильтра питьевой воды",
    "G4397-73": "Смеситель для кухни с подключением фильтра питьевой воды",
    "G905-5": "Многофункциональная стойка напольная",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual verified product name fixes")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply changes to DB. Without this flag the script runs in dry-run mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not MANUAL_NAME_FIXES:
        print("No manual fixes configured.")
        return

    session = SessionLocal()
    changed = 0
    not_found = 0
    unchanged = 0

    try:
        print("=" * 80)
        print("MANUAL PRODUCT NAME FIXES")
        print("=" * 80)
        print(f"Mode: {'COMMIT' if args.commit else 'DRY-RUN'}")
        print()

        for sku, new_name in MANUAL_NAME_FIXES.items():
            item = (
                session.query(models.Product)
                .filter(models.Product.sku == sku)
                .one_or_none()
            )

            if not item:
                print(f"NOT FOUND: {sku}")
                not_found += 1
                continue

            old_name = (item.name or "").strip()
            new_name = (new_name or "").strip()

            if not new_name:
                print(f"SKIP EMPTY TARGET: {sku}")
                unchanged += 1
                continue

            if old_name == new_name:
                print(f"UNCHANGED: {sku} | {old_name}")
                unchanged += 1
                continue

            print(f"SKU: {sku}")
            print(f"OLD: {old_name}")
            print(f"NEW: {new_name}")
            print("-" * 80)

            if args.commit:
                item.name = new_name

            changed += 1

        if args.commit:
            session.commit()
            print("\nCommitted changes.")
        else:
            print("\nDry-run only. No DB changes applied.")

        print("\nSummary:")
        print(f"  Changed candidates: {changed}")
        print(f"  Not found: {not_found}")
        print(f"  Unchanged/skipped: {unchanged}")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
