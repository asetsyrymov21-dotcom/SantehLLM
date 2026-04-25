#!/usr/bin/env python3
"""
CLI entrypoint для импорта остатков (FRAP + GAPPO).

Использует существующий StockImporter с dry-run и commit режимами.
"""

import argparse
import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.services.stock_import.importer import StockImporter
from app.services.stock_import.matcher import StockMatcher
from app.services.stock_import.excel_parser import StockExcelParser
from app.services.post_import.reporting_service import run_post_import_summary


def main():
    parser = argparse.ArgumentParser(
        description="Импорт остатков из Excel (FRAP + GAPPO)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run (по умолчанию) - только покажет что будет изменено
  python scripts/run_stock_import.py --file stock.xlsx

  # Реальное применение изменений
  python scripts/run_stock_import.py --file stock.xlsx --commit
        """,
    )
    parser.add_argument("--file", required=True, help="Путь к Excel файлу с остатками")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Применить изменения в БД (по умолчанию dry-run)",
    )
    args = parser.parse_args()

    # Проверяем что файл существует
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ Ошибка: файл не найден: {file_path}")
        sys.exit(1)

    print("=" * 60)
    print("STOCK IMPORT")
    print("=" * 60)
    print(f"File: {file_path}")
    print(f"Mode: {'COMMIT' if args.commit else 'DRY-RUN'}")
    print()

    session = SessionLocal()
    try:
        # Шаг 1: Парсим Excel
        print("1. Парсинг Excel...")
        parser = StockExcelParser(file_path)
        parse_result = parser.parse()
        print(f"   Найдено строк: {len(parse_result.rows)}")
        print()

        # Шаг 2: Создаём importer и matcher
        importer = StockImporter(
            session=session,
            source_file=str(file_path),
        )
        matcher = StockMatcher(
            session=session,
            brand_filter=None,  # FRAP + GAPPO
        )

        # Шаг 3: Матчинг строк
        print("2. Матчинг SKU с базой данных...")
        report = matcher.match_rows(parse_result.rows)
        report.total_rows_scanned = len(parse_result.rows)
        print(f"   Обработано: {len(report.results)} строк")
        print()

        report.total_rows_scanned = len(parse_result.rows)

        # Export unmatched SKU tail for inspection
        unmatched_report = report.get_unmatched_report()
        if unmatched_report.unmatched_results:
            out_dir = Path("reports")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "unmatched_after_import.csv"
            unmatched_report.to_csv_v2(out_file)
            print(f"   Unmatched exported to: {out_file}")
            print()

        # Шаг 4: Dry-run или Commit
        commit_result = None
        if args.commit:
            print("3. Применение изменений...")
            commit_result = importer.commit(report, skip_duplicates=True)
            commit_result.print_summary()
            print()
            print(f"✅ Импорт завершён. Обновлено: {commit_result.updated}")
        else:
            print("3. Dry-run (изменения не применяются)...")
            importer.dry_run(report)
            print()
            print("💡 Для применения изменений добавьте флаг --commit")

        # Шаг 5: Post-import summary
        print("\n4. Генерация отчёта...")
        try:
            summary_report = run_post_import_summary(
                session=session,
                stock_result=commit_result if args.commit else report,
                run_type="stock_import",
                source_file=str(file_path),
                dry_run=not args.commit,
                save_artifacts=True,
                validate=args.commit,  # Only validate on real runs
            )
            print(f"   Отчёт сохранён: reports/import_report_*.json")
            if summary_report.unmatched_skus:
                print(
                    f"   ⚠️  Найдено {len(summary_report.unmatched_skus)} unmatched SKU"
                )
        except Exception as e:
            print(f"   ⚠️  Ошибка генерации отчёта: {e}")

    except Exception as e:
        print()
        print(f"❌ Ошибка: {e}")
        if args.commit:
            print("🔄 Откат транзакции...")
            session.rollback()
            print("✅ Транзакция откачена")
        raise
    finally:
        session.close()
        print()
        print("Готово.")


if __name__ == "__main__":
    main()
