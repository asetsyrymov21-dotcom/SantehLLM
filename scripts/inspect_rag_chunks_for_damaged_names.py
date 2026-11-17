from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


REPORTS_DIR = Path("reports")
DAMAGED_CSV = REPORTS_DIR / "damaged_product_names.csv"
OUTPUT_CSV = REPORTS_DIR / "damaged_rag_chunk_matches.csv"

DEFAULT_LIMIT = 50


@dataclass
class MatchRow:
    sku: str
    damaged_name: str
    cluster_hint: str
    damage_type: str
    rag_document_id: str
    rag_title: str
    rag_source: str
    chunk_id: str
    chunk_index: str
    chunk_text: str
    match_reason: str


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


def read_damaged_rows(limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
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


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def truncate_text(value: str, limit: int = 300) -> str:
    value = (value or "").strip().replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def build_search_terms(row: dict[str, str]) -> list[tuple[str, str]]:
    name = normalize_text(row.get("name") or "")
    cluster_hint = (row.get("cluster_hint") or "").strip()

    terms: list[tuple[str, str]] = []

    # SKU
    sku = (row.get("sku") or "").strip()
    if sku:
        terms.append(("sku", sku.lower()))

    # Ключевые кластерные маркеры
    cluster_markers = {
        "accessories_blob": ["аксессуаров", "gappo"],
        "g103_mixers_35mm": ["смесителей", "35mm"],
        "gappo_blob": ["gappo"],
        "hygienic_showers_blob": ["гигиенических душей"],
        "shower_heads_blob": ["душевых леек"],
        "embedded_showers_blob": ["встраиваемых", "душей"],
        "shower_system_mixers_blob": ["душевая система", "излив"],
        "truncated_only": [],
    }

    for marker in cluster_markers.get(cluster_hint, []):
        terms.append(("cluster_marker", marker.lower()))

    # Полное повреждённое имя
    if name:
        terms.append(("damaged_name", name))

        # Первые 2-4 слова как fallback
        parts = name.split()
        if len(parts) >= 2:
            terms.append(("name_prefix", " ".join(parts[:2])))
        if len(parts) >= 3:
            terms.append(("name_prefix", " ".join(parts[:3])))
        if len(parts) >= 4:
            terms.append(("name_prefix", " ".join(parts[:4])))

    # Убираем дубли
    deduped: list[tuple[str, str]] = []
    seen = set()
    for reason, term in terms:
        key = (reason, term)
        if term and key not in seen:
            seen.add(key)
            deduped.append((reason, term))

    return deduped


def search_matches_for_row(cur, row: dict[str, str]) -> list[MatchRow]:
    sku = (row.get("sku") or "").strip()
    damaged_name = (row.get("name") or "").strip()
    cluster_hint = (row.get("cluster_hint") or "").strip()
    damage_type = (row.get("damage_type") or "").strip()

    matches: list[MatchRow] = []
    terms = build_search_terms(row)

    for reason, term in terms:
        cur.execute(
            """
            SELECT
                rd.id AS rag_document_id,
                COALESCE(rd.title, '') AS rag_title,
                COALESCE(rd.source, '') AS rag_source,
                rc.id AS chunk_id,
                rc.chunk_index,
                COALESCE(rc.text, '') AS chunk_text
            FROM rag_chunks rc
            JOIN rag_documents rd
              ON rd.id = rc.document_id
            WHERE lower(rc.text) LIKE %s
            ORDER BY rd.id, rc.chunk_index
            LIMIT 5
            """,
            (f"%{term}%",),
        )
        rows = cur.fetchall()

        for db_row in rows:
            matches.append(
                MatchRow(
                    sku=sku,
                    damaged_name=damaged_name,
                    cluster_hint=cluster_hint,
                    damage_type=damage_type,
                    rag_document_id=str(db_row["rag_document_id"]),
                    rag_title=(db_row["rag_title"] or "").strip(),
                    rag_source=(db_row["rag_source"] or "").strip(),
                    chunk_id=str(db_row["chunk_id"]),
                    chunk_index=str(db_row["chunk_index"]),
                    chunk_text=truncate_text(db_row["chunk_text"] or ""),
                    match_reason=f"{reason}: {term}",
                )
            )

    # Убираем дубли по chunk_id + reason
    deduped: list[MatchRow] = []
    seen = set()
    for item in matches:
        key = (item.chunk_id, item.match_reason, item.sku)
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped


def inspect_matches(limit: int = DEFAULT_LIMIT) -> list[MatchRow]:
    damaged_rows = read_damaged_rows(limit=limit)
    results: list[MatchRow] = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for row in damaged_rows:
                results.extend(search_matches_for_row(cur, row))

    results.sort(
        key=lambda x: (
            x.sku,
            x.rag_document_id,
            x.chunk_index,
            x.match_reason,
        )
    )
    return results


def save_csv(rows: list[MatchRow]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "sku",
                "damaged_name",
                "cluster_hint",
                "damage_type",
                "rag_document_id",
                "rag_title",
                "rag_source",
                "chunk_id",
                "chunk_index",
                "chunk_text",
                "match_reason",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row.sku,
                    row.damaged_name,
                    row.cluster_hint,
                    row.damage_type,
                    row.rag_document_id,
                    row.rag_title,
                    row.rag_source,
                    row.chunk_id,
                    row.chunk_index,
                    row.chunk_text,
                    row.match_reason,
                ]
            )


def print_summary(rows: list[MatchRow]) -> None:
    print()
    print(f"Chunk matches found: {len(rows)}")
    print(f"Output CSV: {OUTPUT_CSV}")
    print()

    print("Top 30 matches:")
    print("-" * 180)
    print(f"{'SKU':18} {'doc_id':8} {'chunk':7} {'reason':30} title")
    print("-" * 180)

    for row in rows[:30]:
        print(
            f"{row.sku:18} {row.rag_document_id:8} {row.chunk_index:7} "
            f"{row.match_reason[:30]:30} {row.rag_title[:70]}"
        )

    print("-" * 180)
    print()


def main():
    print("Inspecting rag_chunks for damaged product names...")
    rows = inspect_matches(limit=50)
    save_csv(rows)
    print_summary(rows)


if __name__ == "__main__":
    main()
