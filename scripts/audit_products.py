#!/usr/bin/env python3
"""
Скрипт аудита продуктов.
Только SELECT-запросы, безопасный для прода.

Формирует 6 CSV-отчётов в папке reports/products_audit/
"""

import csv
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Product, Inventory
from app.db.session import SessionLocal


REPORTS_DIR = Path("reports/products_audit")


def ensure_reports_dir() -> None:
    """Создать папку для отчётов, если её нет."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def write_csv(filename: str, fieldnames: list[str], rows: list[dict]) -> int:
    """
    Хелпер для записи CSV.
    Возвращает количество записанных строк.
    """
    filepath = REPORTS_DIR / filename
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def report_products_brand_null(session: Session) -> int:
    """Products с пустым или NULL brand."""
    rows = (
        session.query(Product.id, Product.sku, Product.name, Product.brand)
        .filter((Product.brand.is_(None)) | (func.trim(Product.brand) == ""))
        .all()
    )
    data = [{"id": r.id, "sku": r.sku, "name": r.name, "brand": r.brand} for r in rows]
    return write_csv("products_brand_null.csv", ["id", "sku", "name", "brand"], data)


def report_products_bad_name(session: Session) -> int:
    """Products с некорректным name: NULL, пустой или содержит #ERROR!."""
    rows = (
        session.query(Product.id, Product.sku, Product.name, Product.brand)
        .filter(
            (Product.name.is_(None))
            | (func.trim(Product.name) == "")
            | (Product.name.ilike("%#ERROR!%"))
        )
        .all()
    )
    data = [{"id": r.id, "sku": r.sku, "name": r.name, "brand": r.brand} for r in rows]
    return write_csv("products_bad_name.csv", ["id", "sku", "name", "brand"], data)


def report_products_brand_mismatch(session: Session) -> int:
    """
    Products где brand не соответствует префиксу SKU:
    - F... -> FRAP
    - G... -> GAPPO
    """
    # Берём только SKU на F и G
    rows = (
        session.query(Product.id, Product.sku, Product.name, Product.brand)
        .filter(Product.sku.ilike("F%") | Product.sku.ilike("G%"))
        .all()
    )

    mismatches = []
    for r in rows:
        expected_brand = "FRAP" if r.sku.upper().startswith("F") else "GAPPO"
        brand_normalized = r.brand.strip().upper() if r.brand else None

        # Проверяем mismatch: NULL, пустой или не совпадает
        if (
            brand_normalized is None
            or brand_normalized == ""
            or brand_normalized != expected_brand
        ):
            mismatches.append(
                {
                    "id": r.id,
                    "sku": r.sku,
                    "name": r.name,
                    "brand": r.brand,
                    "expected_brand": expected_brand,
                }
            )

    return write_csv(
        "products_brand_mismatch.csv",
        ["id", "sku", "name", "brand", "expected_brand"],
        mismatches,
    )


def report_products_without_inventory(session: Session) -> int:
    """Products без записи в inventory."""
    # LEFT JOIN + проверка на NULL
    rows = (
        session.query(Product.id, Product.sku, Product.name, Product.brand)
        .outerjoin(Inventory, Product.id == Inventory.product_id)
        .filter(Inventory.id.is_(None))
        .all()
    )
    data = [{"id": r.id, "sku": r.sku, "name": r.name, "brand": r.brand} for r in rows]
    return write_csv(
        "products_without_inventory.csv", ["id", "sku", "name", "brand"], data
    )


def report_inventory_zero_stock(session: Session) -> int:
    """Products с inventory и stock_doc = 0."""
    rows = (
        session.query(
            Product.id,
            Product.sku,
            Product.name,
            Product.brand,
            Inventory.stock_doc,
        )
        .join(Inventory, Product.id == Inventory.product_id)
        .filter(Inventory.stock_doc == 0)
        .all()
    )
    data = [
        {
            "id": r.id,
            "sku": r.sku,
            "name": r.name,
            "brand": r.brand,
            "stock_doc": r.stock_doc,
        }
        for r in rows
    ]
    return write_csv(
        "inventory_zero_stock.csv", ["id", "sku", "name", "brand", "stock_doc"], data
    )


def report_sku_prefix_summary(session: Session) -> int:
    """Агрегированный отчёт по первым буквам SKU."""
    # Используем LEFT(sku, 1) для PostgreSQL
    result = (
        session.query(
            func.upper(func.left(Product.sku, 1)).label("prefix"),
            func.count().label("total"),
        )
        .group_by(func.upper(func.left(Product.sku, 1)))
        .order_by("prefix")
        .all()
    )
    data = [{"prefix": r.prefix, "total": r.total} for r in result]
    return write_csv("sku_prefix_summary.csv", ["prefix", "total"], data)


def main() -> None:
    print("=" * 50)
    print("AUDIT PRODUCTS - Начало аудита")
    print("=" * 50)

    ensure_reports_dir()
    print(f"Отчёты будут сохранены в: {REPORTS_DIR.absolute()}")
    print()

    session = SessionLocal()
    try:
        # Собираем результаты всех отчётов
        results = {}

        print("1. Поиск products с пустым brand...")
        results["products_brand_null"] = report_products_brand_null(session)

        print("2. Поиск products с некорректным name...")
        results["products_bad_name"] = report_products_bad_name(session)

        print("3. Поиск products с несовпадающим brand...")
        results["products_brand_mismatch"] = report_products_brand_mismatch(session)

        print("4. Поиск products без inventory...")
        results["products_without_inventory"] = report_products_without_inventory(
            session
        )

        print("5. Поиск products с нулевым stock_doc...")
        results["inventory_zero_stock"] = report_inventory_zero_stock(session)

        print("6. Формирование сводки по префиксам SKU...")
        results["sku_prefix_summary"] = report_sku_prefix_summary(session)

        # Выводим summary
        print()
        print("=" * 50)
        print("SUMMARY")
        print("=" * 50)
        for report_name, count in results.items():
            print(f"{report_name}: {count}")

        print()
        print(f"Все отчёты сохранены в: {REPORTS_DIR.absolute()}")

    finally:
        session.close()
        print()
        print("Аудит завершён.")


if __name__ == "__main__":
    main()
