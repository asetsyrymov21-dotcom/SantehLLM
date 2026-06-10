from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_TITLE = "GAPPO 2026 catalog products"
DEFAULT_SOURCE = "2026 GAPPOсмесители каталог .pdf"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def validate_dataset(
    *,
    chunks: list[dict[str, Any]],
    products: list[dict[str, Any]],
    indexes: dict[str, Any],
) -> dict[str, Any]:
    product_articles = [product.get("article", "") for product in products]
    chunk_articles = [chunk.get("metadata", {}).get("article", "") for chunk in chunks]
    indexed_articles = set((indexes.get("by_article") or {}).keys())

    product_counts = Counter(product_articles)
    chunk_counts = Counter(chunk_articles)

    empty_product_articles = [idx for idx, article in enumerate(product_articles) if not article]
    empty_chunk_articles = [idx for idx, article in enumerate(chunk_articles) if not article]
    duplicate_product_articles = {
        article: count for article, count in sorted(product_counts.items()) if article and count > 1
    }
    duplicate_chunk_articles = {
        article: count for article, count in sorted(chunk_counts.items()) if article and count > 1
    }

    missing_from_index = sorted(set(product_articles) - indexed_articles)
    index_missing_from_products = sorted(indexed_articles - set(product_articles))

    errors: list[str] = []
    if empty_product_articles:
        errors.append(f"products have empty article at rows: {empty_product_articles[:20]}")
    if empty_chunk_articles:
        errors.append(f"chunks have empty metadata.article at rows: {empty_chunk_articles[:20]}")
    if missing_from_index:
        errors.append(f"products missing from indexes.by_article: {missing_from_index[:20]}")
    if index_missing_from_products:
        errors.append(f"indexes.by_article has articles missing from products: {index_missing_from_products[:20]}")

    return {
        "errors": errors,
        "products": len(products),
        "product_unique_articles": len(set(product_articles)),
        "chunks": len(chunks),
        "chunk_unique_articles": len(set(chunk_articles)),
        "indexed_articles": len(indexed_articles),
        "duplicate_product_articles": duplicate_product_articles,
        "duplicate_chunk_articles": duplicate_chunk_articles,
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"products={report['products']}")
    print(f"product_unique_articles={report['product_unique_articles']}")
    print(f"chunks={report['chunks']}")
    print(f"chunk_unique_articles={report['chunk_unique_articles']}")
    print(f"indexed_articles={report['indexed_articles']}")

    duplicates = report["duplicate_product_articles"]
    if duplicates:
        rendered = ", ".join(f"{article} x{count}" for article, count in duplicates.items())
        print(f"duplicate_product_articles={rendered}")

    chunk_duplicates = report["duplicate_chunk_articles"]
    if chunk_duplicates and chunk_duplicates != duplicates:
        rendered = ", ".join(f"{article} x{count}" for article, count in chunk_duplicates.items())
        print(f"duplicate_chunk_articles={rendered}")

    if report["errors"]:
        print("errors:")
        for error in report["errors"]:
            print(f"- {error}")


def delete_existing_document(title: str, source: str | None) -> int:
    from sqlalchemy import select

    from app.db.rag_models import RagDocument
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        stmt = select(RagDocument).where(RagDocument.title == title)
        if source is None:
            stmt = stmt.where(RagDocument.source.is_(None))
        else:
            stmt = stmt.where(RagDocument.source == source)

        docs = session.scalars(stmt).all()
        for doc in docs:
            session.delete(doc)
        session.commit()
        return len(docs)


def import_chunks(
    *,
    title: str,
    source: str | None,
    chunks: list[dict[str, Any]],
    replace: bool,
) -> int:
    from app.db.session import SessionLocal
    from app.repositories.rag_repository import RagRepository

    if replace:
        deleted = delete_existing_document(title, source)
        if deleted:
            print(f"deleted_existing_documents={deleted}")

    texts = [chunk["text"] for chunk in chunks]
    metadatas = [chunk.get("metadata") or {} for chunk in chunks]

    with SessionLocal() as session:
        repo = RagRepository(session)
        doc = repo.add_document_with_chunks(title=title, source=source, chunks=texts, metadatas=metadatas)
        session.commit()
        print(f"document_id={doc.id}")
    return len(chunks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import GAPPO bot-ready JSONL chunks into RAG tables.")
    parser.add_argument("--rag-chunks", type=Path, default=Path("rag_chunks.jsonl"))
    parser.add_argument("--products", type=Path, default=Path("products.json"))
    parser.add_argument("--indexes", type=Path, default=Path("indexes.json"))
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    chunks = load_jsonl(args.rag_chunks)
    products = load_json(args.products)
    indexes = load_json(args.indexes)

    report = validate_dataset(chunks=chunks, products=products, indexes=indexes)
    print_report(report)
    if report["errors"]:
        raise SystemExit(1)

    if args.dry_run:
        print("dry_run=true")
        return

    imported = import_chunks(
        title=args.title,
        source=args.source,
        chunks=chunks,
        replace=args.replace,
    )
    print(f"imported_chunks={imported}")


if __name__ == "__main__":
    main()
