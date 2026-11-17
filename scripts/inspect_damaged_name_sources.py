from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


REPORTS_DIR = Path("reports")
DAMAGED_CSV = REPORTS_DIR / "damaged_product_names.csv"
OUTPUT_CSV = REPORTS_DIR / "damaged_name_source_inspection.csv"

DEFAULT_LIMIT = 50


@dataclass
class InspectionRow:
    sku: str
    damaged_name: str
    source_table: str
    source_name: str
    source_title: str
    source_text: str
    source_path: str
    source_page: str
    notes: str


def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "santeh"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.environ["POSTGRES_PASSWORD"],
        cursor_factory=RealDictCursor,
    )


def read_damaged_skus(limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
    if not DAMAGED_CSV.exists():
        raise FileNotFoundError(
            f"Не найден файл отчёта: {DAMAGED_CSV}. Сначала запусти python -m scripts.export_damaged_product_names"
        )

    rows: list[dict[str, str]] = []
    with DAMAGED_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            if len(rows) >= limit:
                break

    return rows


def fetch_product_name(cur, sku: str) -> str:
    cur.execute(
        """
        SELECT name
        FROM products
        WHERE sku = %s
        LIMIT 1
        """,
        (sku,),
    )
    row = cur.fetchone()
    if not row:
        return ""
    return (row.get("name") or "").strip()


def list_tables(cur) -> set[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        """
    )
    return {row["table_name"] for row in cur.fetchall()}


def list_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        (table_name,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in columns:
            return c
    return None


def build_dynamic_select(
    table_name: str, columns: set[str], sku: str
) -> tuple[str, list[Any]] | None:
    sku_col = first_existing(
        columns, ["sku", "product_sku", "article", "vendor_code", "code"]
    )
    if not sku_col:
        return None

    name_col = first_existing(columns, ["name", "product_name", "title"])
    title_col = first_existing(columns, ["title", "heading", "header", "product_title"])
    text_col = first_existing(
        columns,
        ["text", "raw_text", "content", "source_text", "chunk_text", "fragment"],
    )
    path_col = first_existing(
        columns, ["source_path", "file_path", "pdf_path", "path", "filename"]
    )
    page_col = first_existing(columns, ["page", "page_no", "page_number"])

    select_parts = [f"{sku_col}::text AS sku"]

    if name_col:
        select_parts.append(f"COALESCE({name_col}::text, '') AS source_name")
    else:
        select_parts.append("'' AS source_name")

    if title_col:
        select_parts.append(f"COALESCE({title_col}::text, '') AS source_title")
    else:
        select_parts.append("'' AS source_title")

    if text_col:
        select_parts.append(f"COALESCE({text_col}::text, '') AS source_text")
    else:
        select_parts.append("'' AS source_text")

    if path_col:
        select_parts.append(f"COALESCE({path_col}::text, '') AS source_path")
    else:
        select_parts.append("'' AS source_path")

    if page_col:
        select_parts.append(f"COALESCE({page_col}::text, '') AS source_page")
    else:
        select_parts.append("'' AS source_page")

    sql = f"""
        SELECT
            {", ".join(select_parts)}
        FROM {table_name}
        WHERE {sku_col} = %s
        LIMIT 3
    """
    return sql, [sku]


def truncate_text(value: str, limit: int = 300) -> str:
    value = (value or "").strip().replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def infer_notes(
    damaged_name: str, source_name: str, source_title: str, source_text: str
) -> str:
    dn = damaged_name.lower()
    sn = source_name.lower()
    st = source_title.lower()
    sx = source_text.lower()

    if dn and sn and dn == sn:
        return "damaged_name matches source_name"
    if dn and st and dn == st:
        return "damaged_name matches source_title"
    if dn and sx and dn in sx:
        return "damaged_name appears inside source_text"
    if sn and sx and sn in sx:
        return "source_name appears inside source_text"
    if st and sx and st in sx:
        return "source_title appears inside source_text"
    return "manual review"


def inspect_sources(limit: int = DEFAULT_LIMIT) -> list[InspectionRow]:
    damaged_rows = read_damaged_skus(limit=limit)

    candidate_tables = [
        "product_import_rows",
        "product_import_items",
        "product_source_rows",
        "product_sources",
        "import_rows",
        "import_items",
        "source_rows",
        "source_items",
        "staging_products",
        "raw_products",
        "raw_product_rows",
        "parsed_products",
        "parsed_product_rows",
        "product_chunks",
        "chunks",
        "documents",
    ]

    results: list[InspectionRow] = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            available_tables = list_tables(cur)

            for damaged in damaged_rows:
                sku = (damaged.get("sku") or "").strip()
                if not sku:
                    continue

                damaged_name = fetch_product_name(cur, sku)
                found_any = False

                for table_name in candidate_tables:
                    if table_name not in available_tables:
                        continue

                    columns = list_columns(cur, table_name)
                    built = build_dynamic_select(table_name, columns, sku)
                    if not built:
                        continue

                    sql, params = built
                    try:
                        cur.execute(sql, params)
                        rows = cur.fetchall()
                    except Exception:
                        conn.rollback()
                        continue

                    if not rows:
                        continue

                    found_any = True
                    for row in rows:
                        source_name = (row.get("source_name") or "").strip()
                        source_title = (row.get("source_title") or "").strip()
                        source_text = truncate_text(row.get("source_text") or "")
                        source_path = (row.get("source_path") or "").strip()
                        source_page = (row.get("source_page") or "").strip()

                        notes = infer_notes(
                            damaged_name=damaged_name,
                            source_name=source_name,
                            source_title=source_title,
                            source_text=source_text,
                        )

                        results.append(
                            InspectionRow(
                                sku=sku,
                                damaged_name=damaged_name,
                                source_table=table_name,
                                source_name=source_name,
                                source_title=source_title,
                                source_text=source_text,
                                source_path=source_path,
                                source_page=source_page,
                                notes=notes,
                            )
                        )

                if not found_any:
                    results.append(
                        InspectionRow(
                            sku=sku,
                            damaged_name=damaged_name,
                            source_table="NOT_FOUND",
                            source_name="",
                            source_title="",
                            source_text="",
                            source_path="",
                            source_page="",
                            notes="No matching candidate source rows found",
                        )
                    )

    return results


def save_csv(rows: list[InspectionRow]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "sku",
                "damaged_name",
                "source_table",
                "source_name",
                "source_title",
                "source_text",
                "source_path",
                "source_page",
                "notes",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row.sku,
                    row.damaged_name,
                    row.source_table,
                    row.source_name,
                    row.source_title,
                    row.source_text,
                    row.source_path,
                    row.source_page,
                    row.notes,
                ]
            )


def print_summary(rows: list[InspectionRow]) -> None:
    print()
    print(f"Inspection rows: {len(rows)}")
    print(f"Output CSV: {OUTPUT_CSV}")
    print()

    print("Top 30:")
    print("-" * 160)
    print(f"{'SKU':18} {'source_table':24} {'notes':34} damaged_name")
    print("-" * 160)

    for row in rows[:30]:
        print(
            f"{row.sku:18} {row.source_table:24} {row.notes:34} {truncate_text(row.damaged_name, 70)}"
        )

    print("-" * 160)
    print()


def main():
    print("Inspecting damaged product name sources...")
    rows = inspect_sources(limit=50)
    save_csv(rows)
    print_summary(rows)


if __name__ == "__main__":
    main()
