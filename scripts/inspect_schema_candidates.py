from __future__ import annotations

import os
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor


INTERESTING_COLUMN_PATTERNS = [
    "sku",
    "name",
    "title",
    "text",
    "content",
    "raw",
    "source",
    "path",
    "file",
    "page",
    "pdf",
    "chunk",
    "product",
    "import",
    "article",
    "code",
]


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


def is_interesting_column(column_name: str) -> bool:
    c = column_name.lower()
    return any(pattern in c for pattern in INTERESTING_COLUMN_PATTERNS)


def main():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            rows = cur.fetchall()

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["table_name"]].append((row["column_name"], row["data_type"]))

    print()
    print("=== ALL TABLES ===")
    for table_name in sorted(grouped.keys()):
        print(table_name)

    print()
    print("=== INTERESTING TABLES ===")
    for table_name in sorted(grouped.keys()):
        interesting = [
            col for col, _dtype in grouped[table_name] if is_interesting_column(col)
        ]
        if interesting:
            print(f"\n[{table_name}]")
            for col, dtype in grouped[table_name]:
                marker = "*" if is_interesting_column(col) else " "
                print(f"  {marker} {col:30} {dtype}")


if __name__ == "__main__":
    main()
