from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import or_

from app.db import SessionLocal, models
import re


SUSPICIOUS_PREFIXES = [
    "G4395-",
    "G4397-",
    "G4398-",
    "G905-",
]

SUSPICIOUS_EXACT = [
    "G4399-86",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review suspicious GAPPO sku/name mismatches without changing DB"
    )
    parser.add_argument(
        "--brand",
        required=True,
        help="Brand name to inspect, e.g. GAPPO",
    )
    parser.add_argument(
        "--out",
        default="reports/gappo_suspicious_review.csv",
        help="Path to output CSV report",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def detect_cluster(sku: str) -> str:
    sku = normalize_text(sku)
    for prefix in SUSPICIOUS_PREFIXES:
        if sku.startswith(prefix):
            return prefix.rstrip("*")
    for exact in SUSPICIOUS_EXACT:
        if sku == exact:
            return exact
    return "other"


import re


import re


def classify_case(row: dict[str, Any]) -> tuple[str, str, str]:
    """
    Returns:
        reason, suggested_action, confidence
    """
    sku = normalize_text(row.get("sku"))
    name = normalize_text(row.get("name"))

    if not name:
        return ("empty_name", "manual_review", "high")

    lowered = name.lower()
    compact = " ".join(name.split())

    garbage_signals = [
        "gappo g95",
        "gappo g98",
        "аксессуаров",
        "смесителей (латунь)",
        "матери",
        "35mm",
        "сатин 35",
        "золо",
        "ч x е р",
    ]

    clean_name_signals = [
        "смеситель для кухни с подключением фильтра питьевой воды",
        "смеситель для кухни с выдвижным изливом",
        "смеситель для кухни с гибким изливом",
    ]

    # 1. Чистое имя без SKU в начале — это тоже ok
    if any(signal in lowered for signal in clean_name_signals):
        has_other_sku_refs = (
            len(re.findall(r"\bG\d{3,5}-\d+\b", name, flags=re.IGNORECASE)) >= 1
        )
        has_garbage = any(signal in lowered for signal in garbage_signals)

        if not has_other_sku_refs and not has_garbage:
            return ("clean_name_without_leading_sku", "ok", "high")

    # 2. Нормальный случай: имя начинается с SKU и дальше идет чистое имя
    if sku and compact.startswith(sku + " "):
        tail = compact[len(sku) :].strip()

        has_suspicious_tail = any(signal in tail.lower() for signal in garbage_signals)
        has_other_sku_refs = (
            len(re.findall(r"\bG\d{3,5}-\d+\b", tail, flags=re.IGNORECASE)) >= 1
        )

        if not has_suspicious_tail and not has_other_sku_refs:
            return ("clean_name_with_leading_sku", "ok", "high")

    # 3. Явная грязь
    if re.search(r"\bG\d{3,5}-\d+\b.*\bG\d{3,5}-\d+\b", name, flags=re.IGNORECASE):
        return ("multiple_sku_refs_in_name", "manual_review", "high")

    if any(signal in lowered for signal in garbage_signals):
        return ("catalog_garbage_or_series_text_in_name", "manual_review", "high")

    # 4. Обрыв / возможный drift
    if (
        len(name) < 20
        or name.endswith(" G")
        or name.endswith(" /")
        or name.endswith(" -")
    ):
        return ("possible_page_local_name_binding_drift", "page_local_guard", "medium")

    return ("needs_manual_review", "manual_review", "low")


def fetch_rows(session, brand: str) -> list[dict[str, Any]]:
    filters = []

    for prefix in SUSPICIOUS_PREFIXES:
        filters.append(models.Product.sku.like(f"{prefix}%"))

    for exact in SUSPICIOUS_EXACT:
        filters.append(models.Product.sku == exact)

    query = (
        session.query(models.Product)
        .filter(models.Product.brand == brand)
        .filter(or_(*filters))
        .order_by(models.Product.sku.asc())
    )

    items = query.all()
    rows: list[dict[str, Any]] = []

    for item in items:
        sku = normalize_text(getattr(item, "sku", ""))
        name = normalize_text(getattr(item, "name", ""))
        brand_value = normalize_text(getattr(item, "brand", ""))
        page = None

        cluster = detect_cluster(sku)
        reason, suggested_action, confidence = classify_case(
            {
                "sku": sku,
                "name": name,
                "brand": brand_value,
                "page": page,
            }
        )

        rows.append(
            {
                "sku": sku,
                "name": name,
                "brand": brand_value,
                "page": page,
                "cluster": cluster,
                "reason": reason,
                "suggested_action": suggested_action,
                "confidence": confidence,
            }
        )

    return rows


def write_csv(rows: list[dict[str, Any]], out_path: str) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "sku",
        "name",
        "brand",
        "page",
        "cluster",
        "reason",
        "suggested_action",
        "confidence",
    ]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return path


def print_summary(rows: list[dict[str, Any]], csv_path: Path) -> None:
    print("=" * 80)
    print("SUSPICIOUS GAPPO REVIEW REPORT")
    print("=" * 80)
    print(f"Total found: {len(rows)}")

    by_cluster = Counter(row["cluster"] for row in rows)
    by_action = Counter(row["suggested_action"] for row in rows)

    print("\nCounts by cluster:")
    for cluster, count in sorted(by_cluster.items()):
        print(f"  {cluster}: {count}")

    print("\nCounts by suggested_action:")
    for action, count in sorted(by_action.items()):
        print(f"  {action}: {count}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["suggested_action"] != "ok":
            grouped[row["cluster"]].append(row)

    print("\nDetailed grouped preview:")
    for cluster in sorted(grouped.keys()):
        print(f"\n[{cluster}]")
        for row in grouped[cluster][:20]:
            print(
                f"  sku={row['sku']} | page={row['page']} | "
                f"action={row['suggested_action']} | reason={row['reason']} | "
                f"name={row['name']}"
            )
        if len(grouped[cluster]) > 20:
            print(f"  ... and {len(grouped[cluster]) - 20} more")

    print(f"\nCSV written to: {csv_path}")


def main() -> None:
    args = parse_args()

    session = SessionLocal()
    try:
        rows = fetch_rows(session, args.brand)
        csv_path = write_csv(rows, args.out)
        print_summary(rows, csv_path)
        print_g4398_focus(rows)
        print_cluster_neighbors(session, args.brand, "G4398-", rows)
    finally:
        session.close()


def print_g4398_focus(rows: list[dict[str, Any]]) -> None:
    focused = [
        row
        for row in rows
        if row["cluster"] == "G4398-" and row["suggested_action"] != "ok"
    ]

    if not focused:
        print("\nNo focused G4398 dirty cases found.")
        return

    print("\n" + "=" * 80)
    print("FOCUSED G4398 DIRTY CLUSTER REVIEW")
    print("=" * 80)

    for row in focused:
        print(f"SKU: {row['sku']}")
        print(f"Current name: {row['name']}")
        print("Suggested status: manual_name_recovery_needed")
        print(
            "Comment: current name looks like catalog/series garbage, not safe for blind auto-clean"
        )
        print("-" * 80)


def print_cluster_neighbors(
    session, brand: str, prefix: str, rows: list[dict[str, Any]]
) -> None:
    dirty_skus = {
        row["sku"]
        for row in rows
        if row["cluster"] == prefix and row["suggested_action"] != "ok"
    }

    items = (
        session.query(models.Product)
        .filter(models.Product.brand == brand)
        .filter(models.Product.sku.like(f"{prefix}%"))
        .order_by(models.Product.sku.asc())
        .all()
    )

    print("\n" + "=" * 80)
    print(f"NEIGHBOR REVIEW FOR {prefix}*")
    print("=" * 80)

    for item in items:
        sku = normalize_text(getattr(item, "sku", ""))
        name = normalize_text(getattr(item, "name", ""))

        marker = ""
        if sku in dirty_skus:
            marker = "  <-- DIRTY CANDIDATE"

        print(f"{sku} | {name}{marker}")


if __name__ == "__main__":
    main()
