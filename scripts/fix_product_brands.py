#!/usr/bin/env python3
"""
Скрипт исправления брендов продуктов.

Логика:
- F* -> FRAP
- G* -> GAPPO

По умолчанию dry-run (ничего не меняет).
Реальные изменения только с флагом --commit.
"""

import argparse
import csv
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Product
from app.db.session import SessionLocal


REPORTS_DIR = Path("reports/products_audit")
PREVIEW_CSV = "products_brand_fixes_preview.csv"


def ensure_reports_dir() -> None:
    """Создать папку для отчётов, если её нет."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def write_csv(filename: str, fieldnames: list[str], rows: list[dict]) -> None:
    """Хелпер для записи CSV."""
    filepath = REPORTS_DIR / filename
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV сохранён: {filepath}")


def get_expected_brand(sku: str) -> str:
    """Определить ожидаемый бренд по SKU."""
    if sku.upper().startswith("F"):
        return "FRAP"
    elif sku.upper().startswith("G"):
        return "GAPPO"
    return ""


def needs_fix(brand: str | None, expected: str) -> bool:
    """Проверить, нужно ли обновлять brand."""
    if brand is None:
        return True
    brand_clean = brand.strip()
    if brand_clean == "":
        return True
    if brand_clean.upper() != expected.upper():
        return True
    return False


def fix_product_brands(session: Session, commit: bool = False) -> dict:
    """
    Найти и (опционально) исправить бренды продуктов.
    
    Returns:
        dict со статистикой операции
    """
    # Находим все кандидаты (SKU на F и G)
    candidates = (
        session.query(Product)
        .filter(Product.sku.ilike("F%") | Product.sku.ilike("G%"))
        .all()
    )

    scanned_f = 0
    scanned_g = 0
    to_fix = []
    to_frap = 0
    to_gappo = 0

    for product in candidates:
        expected = get_expected_brand(product.sku)
        if not expected:
            continue

        if product.sku.upper().startswith("F"):
            scanned_f += 1
        else:
            scanned_g += 1

        if needs_fix(product.brand, expected):
            to_fix.append({
                "id": product.id,
                "sku": product.sku,
                "name": product.name,
                "old_brand": product.brand,
                "new_brand": expected,
                "product": product,  # ссылка для обновления
            })
            if expected == "FRAP":
                to_frap += 1
            else:
                to_gappo += 1

    # Сохраняем preview CSV
    csv_rows = [
        {
            "id": item["id"],
            "sku": item["sku"],
            "name": item["name"],
            "old_brand": item["old_brand"],
            "new_brand": item["new_brand"],
        }
        for item in to_fix
    ]
    write_csv(PREVIEW_CSV, ["id", "sku", "name", "old_brand", "new_brand"], csv_rows)

    updated_total = 0

    if commit and to_fix:
        print(f"\nПрименяем изменения ({len(to_fix)} записей)...")
        for item in to_fix:
            product = item["product"]
            product.brand = item["new_brand"]
            updated_total += 1
        
        session.commit()
        print(f"Commit выполнен. Обновлено: {updated_total}")
    elif commit:
        print("\nНечего обновлять.")
    else:
        print(f"\nDry-run mode: изменения НЕ применены.")
        print(f"Для применения запустите с флагом --commit")

    return {
        "scanned_f_candidates": scanned_f,
        "scanned_g_candidates": scanned_g,
        "to_fix_total": len(to_fix),
        "to_frap": to_frap,
        "to_gappo": to_gappo,
        "updated_total": updated_total if commit else 0,
        "mode": "commit" if commit else "dry-run",
    }


def print_summary(stats: dict) -> None:
    """Вывести summary статистики."""
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"scanned_f_candidates: {stats['scanned_f_candidates']}")
    print(f"scanned_g_candidates: {stats['scanned_g_candidates']}")
    print(f"to_fix_total: {stats['to_fix_total']}")
    print(f"to_frap: {stats['to_frap']}")
    print(f"to_gappo: {stats['to_gappo']}")
    print(f"updated_total: {stats['updated_total']}")
    print(f"mode={stats['mode']}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Исправление брендов продуктов (F->FRAP, G->GAPPO)"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Применить изменения в БД (по умолчанию dry-run)"
    )
    args = parser.parse_args()

    print("=" * 50)
    print("FIX PRODUCT BRANDS")
    print("=" * 50)
    print(f"Mode: {'COMMIT' if args.commit else 'DRY-RUN'}")
    print()

    ensure_reports_dir()

    session = SessionLocal()
    try:
        stats = fix_product_brands(session, commit=args.commit)
        print_summary(stats)
    except Exception as e:
        if args.commit:
            session.rollback()
            print(f"\nОшибка! Транзакция откачена: {e}")
        else:
            print(f"\nОшибка: {e}")
        raise
    finally:
        session.close()
        print("\nГотово.")


if __name__ == "__main__":
    main()